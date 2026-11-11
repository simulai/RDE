"""RDE 引擎：所有写操作 = 状态机检查 → 追加事件 → 应用到读模型 → （基础节点变化时）影响报告。

数据流见 docs/architecture.md §3。绕过本类直接修改 self.state 不受保护；
一致性由 replay(state_digest) 与测试保证。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from .errors import IllegalTransition, ValidationError, RDEError
from .events import EventLog
from .events.replay import apply, empty_state, replay, state_digest
from .graph import ResearchGraph, validate_node, validate_edge
from .versioning import bump_version, fork_node
from .dependency_analysis import propagate
from . import state_machine as sm


def _default_states(node: dict) -> dict:
    """非 Claim 节点的最小状态维度缺省（仅为结构完整，不授予任何结论）。"""
    n = dict(node)
    if n["type"] in ("assumption", "definition", "claim"):
        n.setdefault("proposition_state", "unknown")
        n.setdefault("evidence_state", "none")
    n.setdefault("work_state", "proposed")
    return n


class RDE:
    """最小研究内核入口。"""

    def __init__(self, log: EventLog | list | tuple | None = None):
        # 入口完整性：无论何种载入形式，都先做哈希链校验（F-A6 修复：曾存在
        # 『传入未校验 EventLog 实例即绕过链校验』的入口不一致）。
        if isinstance(log, (list, tuple)):
            log = EventLog(list(log))
        self.log = log if log is not None else EventLog()
        self.log.verify_chain()
        self.state = replay(self.log.events)
        self.graph = ResearchGraph(self.state)

    # ------------------------------------------------------------ 基础设施
    def _emit(self, type: str, *, actor: str, target: list[str], payload: dict) -> dict:
        ev = self.log.append(type, actor=actor, target=target, payload=payload)
        apply(self.state, ev)
        return ev

    def verify(self) -> bool:
        """哈希链完整性（原则 8：历史不可被静默覆盖）。"""
        return self.log.verify_chain()

    def digest(self) -> str:
        return state_digest(self.state)

    def state_at(self, seq: int) -> dict:
        """时间点重建（验收标准 2：旧版本回溯）。"""
        return replay(self.log.events, upto=seq)

    def save(self, path: str | Path) -> None:
        self.log.save_jsonl(path)

    @classmethod
    def restore(cls, path: str | Path) -> "RDE":
        return cls(EventLog.load_jsonl(path))

    # ------------------------------------------------------------ 结构操作
    def _ensure_new_node(self, node_id: str) -> None:
        """创建入口前置存在性检查（F-A8 审计修复）。

        _emit 的顺序是先 append 日志、再 apply；若 apply 因『重复创建』抛错，
        该事件已写入日志 → 引擎自身日志将无法重放（毒化）。因此所有创建类
        入口必须在写日志之前拒绝，重复创建的防线才有意义。
        """
        if self.graph.get(node_id) is not None:
            raise ValidationError(f"节点已存在: {node_id}（事件溯源不允许覆盖）")

    def create_node(self, node: dict, *, actor: str = "human") -> dict:
        node = _default_states(node)
        validate_node(node)
        self._ensure_new_node(node["id"])
        ev = self._emit("node_created", actor=actor, target=[node["id"]], payload={"node": node})
        return ev

    def create_edge(self, edge: dict, *, actor: str = "human") -> dict:
        validate_edge(edge)
        if edge["id"] in self.graph.edges:
            raise ValidationError(f"边已存在: {edge['id']}（事件溯源不允许覆盖）")
        missing = [n for n in (*edge["premises"], *edge["conclusions"]) if self.graph.get(n) is None]
        if missing:
            raise ValidationError(f"边 {edge['id']} 引用了不存在的节点: {sorted(set(missing))}")
        return self._emit("edge_created", actor=actor, target=[edge["id"]], payload={"edge": edge})

    def revise_node(self, node_id: str, changes: dict, *, actor: str = "human", reason: str | None = None) -> dict:
        """内容/定义修改：产生新版本 + 必须的依赖影响报告（原则 7、验收标准 2/7）。"""
        old = self.graph.require(node_id)
        new = bump_version(old, changes)
        validate_node(new)
        self._emit("node_version_created", actor=actor, target=[node_id],
                   payload={"node": new, "reason": reason or ""})
        return self.impact({node_id: "modified"}, actor="system")

    def fork_definition(self, node_id: str, new_id: str, *, actor: str = "human",
                        changes: dict | None = None) -> dict:
        """Fork Definition（M6）：原对象不动，新 ID 分叉。"""
        original = self.graph.require(node_id)
        forked = fork_node(original, new_id, changes)
        validate_node(forked)
        self._ensure_new_node(new_id)
        self._emit("node_created", actor=actor, target=[new_id], payload={"node": forked})
        self._emit("fork_created", actor=actor, target=[new_id],
                   payload={"original": node_id, "fork": new_id})
        return forked

    def supersede(self, old_id: str, new_node: dict, *, actor: str = "human",
                  reason: str = "") -> dict:
        """新对象取代旧对象（旧对象仍可回溯，不删除）。"""
        new_node = _default_states(new_node)
        validate_node(new_node)
        self._ensure_new_node(new_node["id"])
        self._emit("node_created", actor=actor, target=[new_node["id"]], payload={"node": new_node})
        old = self.graph.require(old_id)
        if old.get("work_state") != "superseded":
            self.set_work_state(old_id, "superseded", actor=actor, reason=reason)
        self._emit("superseded", actor=actor, target=[old_id],
                   payload={"old": old_id, "new": new_node["id"]})
        self.create_edge({
            "id": f"edge-sup-{uuid.uuid4().hex[:8]}",
            "type": "supersedes", "category": "structural",
            "premises": [new_node["id"]], "conclusions": [old_id],
            "created_at": self.log.events[-1]["timestamp"],
            "source": {"origin": "derived"}, "scope": "global",
            "validity": "active",
            "bound_versions": [{"id": old_id, "version": old["version"]}],
        }, actor=actor)
        return self.impact({old_id: "superseded"}, actor="system")

    # ------------------------------------------------------------ 状态转换
    def set_proposition_state(
        self, node_id: str, to_state: str, *,
        justification: dict, actor: str = "human", proposed_only: bool = False,
    ) -> dict:
        node = self.graph.require(node_id)
        frm = node.get("proposition_state")
        # F-E01（原则 10 / architecture §5）：非 human actor 不得*执行*真值语义升级，
        # 只能写入 proposed_only 提议（提议本身不改变状态）。
        if (
            to_state in ("true_in_scope", "false_in_scope")
            and not proposed_only
            and actor != "human"
        ):
            raise IllegalTransition(
                f"actor={actor} 不得执行命题语义状态升级 {frm} → {to_state}"
                "（原则 10：Agent 不得以自我评价授予语义状态）；"
                "请使用 proposed_only 提议并由 human 批准执行"
            )
        if not proposed_only:
            sm.check_proposition_transition(frm, to_state, justification=justification,
                                            scope=node.get("scope"))
        ev = self._emit(
            "proposition_state_changed", actor=actor, target=[node_id],
            payload={"from": frm, "to": to_state, "justification": justification,
                     **({"proposed_only": True} if proposed_only else {})},
        )
        return ev

    def set_evidence_state(self, node_id: str, to_state: str, *, driven_by: list[str],
                           actor: str = "system") -> dict:
        node = self.graph.require(node_id)
        frm = node.get("evidence_state")
        sm.check_evidence_transition(frm, to_state, driven_by=driven_by)
        # 冲突不被覆盖（docs/state_semantics.md §2.1）：方向反转必须显式失效流程
        if (frm, to_state) in (("supported", "contradicted"), ("contradicted", "supported")) \
                and "evidence_invalidated" not in driven_by:
            raise IllegalTransition(
                f"{frm} → {to_state} 必须经 mixed 或 evidence_invalidated 显式失效流程"
                "（单步覆盖冲突是非法的）"
            )
        return self._emit("evidence_state_changed", actor=actor, target=[node_id],
                          payload={"from": frm, "to": to_state, "driven_by": list(driven_by)})

    def set_work_state(self, node_id: str, to_state: str, *, actor: str = "human",
                       reopen: bool = False, reason: str = "") -> dict:
        node = self.graph.require(node_id)
        frm = node.get("work_state")
        sm.check_work_transition(frm, to_state, reopen=reopen)
        # L3（state_semantics §4）：Claim → completed 前，证明义务必须全部完成。
        if node.get("type") == "claim" and to_state == "completed":
            obligations = node.get("proof_obligations") or []
            if not obligations:
                raise IllegalTransition("L3: Claim 缺少证明义务记录，不得 completed")
            open_ids = [o.get("id") for o in obligations
                        if o.get("status") not in ("discharged", "withdrawn")]
            if open_ids:
                raise IllegalTransition(
                    f"L3: 证明义务未完成 {open_ids}，Claim 不得 completed"
                    "（数学轨/经验轨各有验收路径，state_semantics L3）"
                )
        payload = {"from": frm, "to": to_state, "reason": reason}
        if reopen:
            payload["reopen"] = True
        return self._emit("work_state_changed", actor=actor, target=[node_id], payload=payload)

    def refute(self, node_id: str, *, actor: str = "human",
               assumptions: list | None = None, note: str = "") -> dict:
        """反例/推翻：语义状态离开 true/unknown → false_in_scope（原则 5 的执行路径之一）。"""
        node = self.graph.require(node_id)
        binding = assumptions if assumptions is not None else (
            node.get("assumptions") or [{"id": node_id, "version": node["version"]}]
        )
        justification = {"route": "refutation", "assumptions": binding, "note": note}
        ev = self.set_proposition_state(node_id, "false_in_scope", justification=justification,
                                        actor=actor)
        self.impact({node_id: "refuted"}, actor="system")
        return ev

    # ------------------------------------------------------------ 推导（数学轨）
    def start_derivation(self, derivation: dict, *, actor: str = "human") -> dict:
        derivation = _default_states(derivation)
        validate_node(derivation)
        if derivation.get("status") is None:
            derivation["status"] = "draft"
        self._ensure_new_node(derivation["id"])
        return self._emit("derivation_started", actor=actor, target=[derivation["id"]],
                          payload={"derivation": derivation})

    def complete_derivation(self, derivation_id: str, *, actor: str = "human") -> dict:
        d = self.graph.require(derivation_id)
        if d["type"] != "derivation":
            raise RDEError(f"{derivation_id} 不是 derivation")
        return self._emit("derivation_completed", actor=actor, target=[derivation_id],
                          payload={"reason": ""})

    def invalidate_derivation(self, derivation_id: str, *, reason: str,
                              actor: str = "human") -> dict:
        self.graph.require(derivation_id)
        ev = self._emit("derivation_invalidated", actor=actor, target=[derivation_id],
                        payload={"reason": reason})
        self.impact({derivation_id: "modified"}, actor="system")
        return ev

    # ------------------------------------------------------------ 证据（经验轨）
    def append_evidence(self, evidence: dict, *, actor: str = "human") -> dict:
        evidence = _default_states(evidence)
        validate_node(evidence)
        self._ensure_new_node(evidence["id"])
        ev = self._emit("evidence_appended", actor=actor, target=[evidence["id"]],
                        payload={"evidence": evidence})
        targets = sorted(set(evidence.get("supports", [])) | set(evidence.get("contradicts", [])))
        for claim_id in targets:
            if self.graph.get(claim_id) is None:
                raise ValidationError(f"证据 {evidence['id']} 引用了不存在的命题 {claim_id}")
            self._recompute_evidence_state(claim_id, driver="evidence_appended",
                                           actor="system", evidence_id=evidence["id"])
        return ev

    def invalidate_evidence(self, evidence_id: str, *, reason: str,
                            actor: str = "human") -> list[dict]:
        ev_node = self.graph.require(evidence_id)
        if ev_node["type"] != "evidence":
            raise RDEError(f"{evidence_id} 不是 evidence")
        events = [self._emit("evidence_invalidated", actor=actor, target=[evidence_id],
                             payload={"evidence_id": evidence_id, "reason": reason})]
        targets = sorted(set(ev_node.get("supports", [])) | set(ev_node.get("contradicts", [])))
        for claim_id in targets:
            claim = self.graph.require(claim_id)
            if claim.get("evidence_state") not in (None, "none", "invalidated"):
                events.append(self.set_evidence_state(
                    claim_id, "invalidated", driven_by=["evidence_invalidated"], actor="system"))
            events.extend(self._recompute_evidence_state(
                claim_id, driver="evidence_invalidated", actor="system", evidence_id=evidence_id))
        return events

    def withdraw_evidence(self, evidence_id: str, *, reason: str,
                          actor: str = "human") -> list[dict]:
        """证据撤回（source retraction）：validity=withdrawn，随后重算证据状态。

        与 invalidate 的语义区别：撤回=来源撤回；失效=判定/数据错误。
        两者都经显式事件 + 重算（F-D1 审计修复：evidence_withdrawn 的事件类型与
        重放 handler 一直存在，但缺引擎 API，导致文档承诺的"撤回"路径不可达）。
        """
        ev_node = self.graph.require(evidence_id)
        if ev_node["type"] != "evidence":
            raise RDEError(f"{evidence_id} 不是 evidence")
        if ev_node.get("validity") == "withdrawn":
            raise IllegalTransition(f"{evidence_id} 已撤回，禁止重复撤回")
        events = [self._emit("evidence_withdrawn", actor=actor, target=[evidence_id],
                             payload={"evidence_id": evidence_id, "reason": reason})]
        targets = sorted(set(ev_node.get("supports", [])) | set(ev_node.get("contradicts", [])))
        for claim_id in targets:
            claim = self.graph.require(claim_id)
            if claim.get("evidence_state") not in (None, "none", "invalidated"):
                events.append(self.set_evidence_state(
                    claim_id, "invalidated", driven_by=["evidence_withdrawn"], actor="system"))
            events.extend(self._recompute_evidence_state(
                claim_id, driver="evidence_withdrawn", actor="system", evidence_id=evidence_id))
        return events

    def _recompute_evidence_state(self, claim_id: str, *, driver: str, actor: str,
                                  evidence_id: str) -> list[dict]:
        """由证据集合重算命题证据状态，并按转换表（必要时经 invalidated 中转）发事件。"""
        claim = self.graph.require(claim_id)
        relevant = self.graph.evidence_touching(claim_id)
        valid = [e for e in relevant if e.get("validity", "valid") == "valid"]
        sup = [e for e in valid if claim_id in e.get("supports", [])]
        con = [e for e in valid if claim_id in e.get("contradicts", [])]

        def sufficient(e: dict) -> bool:
            return e.get("sufficiency", "sufficient") != "insufficient"

        if not valid:
            target = "invalidated" if relevant else "none"
        elif sup and con:
            target = "mixed"
        elif sup:
            target = "supported" if any(sufficient(e) for e in sup) else "insufficient"
        elif con:
            target = "contradicted" if any(sufficient(e) for e in con) else "insufficient"
        else:
            target = "insufficient"

        frm = claim.get("evidence_state", "none")
        if target == frm:
            return []
        # 防护：未经失效流程不得 supported → contradicted（状态表 §2.1）
        if (frm, target) == ("supported", "contradicted") and driver != "evidence_invalidated":
            raise IllegalTransition(
                "supported → contradicted 必须经冲突(mixed)或显式失效流程（冲突不被覆盖）"
            )
        path = sm.transition_path_evidence(frm, target)
        if path is None:
            raise IllegalTransition(f"无法从证据状态 {frm} 到达 {target}（含中转）")
        events = []
        current = frm
        for nxt in [*path, target]:
            sm.check_evidence_transition(current, nxt, driven_by=[driver])
            events.append(self.set_evidence_state(claim_id, nxt, driven_by=[driver], actor=actor))
            current = nxt
        return events

    # ------------------------------------------------------------ 决策（M7）
    def record_decision(self, decision: dict, *, node_id: str | None = None,
                        actor: str = "human", scope: str = "project") -> str:
        node_id = node_id or f"decision-{uuid.uuid4().hex[:8]}"
        node = _default_states({
            "id": node_id, "type": "decision", "version": 1,
            "created_at": self.log.events[-1]["timestamp"] if self.log.events else "1970-01-01T00:00:00Z",
            "source": {"origin": "human" if actor == "human" else "agent"},
            "scope": scope,
            "content": decision.get("goal", ""),
            "decision": decision,
            "work_state": "completed",
        })
        validate_node(node)
        self._ensure_new_node(node_id)
        self._emit("node_created", actor=actor, target=[node_id], payload={"node": node})
        self._emit("decision_recorded", actor=actor, target=[node_id], payload={"decision": decision})
        return node_id

    def backfill_decision(self, node_id: str, *, actual_outcome: str | None,
                          decision_effective: bool | None,
                          external_validation_ref: str | None = None,
                          actor: str = "human") -> dict:
        """回填决策实际结果（M7：决策是否有效）。"""
        node = self.graph.require(node_id)
        # F-E04（原则 10）：决策有效性判定需人类签署或外部验证引用，agent 不得自评生效。
        if (
            decision_effective is not None
            and actor != "human"
            and not external_validation_ref
        ):
            raise IllegalTransition(
                f"actor={actor} 不得自评 decision_effective（原则 10）："
                "需 human 签署，或提供 external_validation_ref（外部验证引用）"
            )
        decision = dict(node["decision"])
        decision["actual_outcome"] = actual_outcome
        decision["decision_effective"] = decision_effective
        decision["external_validation_ref"] = external_validation_ref
        new = bump_version(node, {"decision": decision}, forbid_state_fields=True)
        self._emit("node_version_created", actor=actor, target=[node_id],
                   payload={"node": new, "reason": "decision backfill (M7)"})
        self._emit("decision_recorded", actor=actor, target=[node_id], payload={"decision": decision})
        return new

    # ------------------------------------------------------------ 分支（M6）
    def branch(self, branch_id: str, *, actor: str = "human", base_seq: int | None = None) -> dict:
        return {"branch_id": branch_id,
                **self._emit("branch_created", actor=actor, target=[branch_id],
                             payload={"branch_id": branch_id,
                                      "base_seq": base_seq if base_seq is not None else len(self.log) - 1})}

    def merge_branch(self, branch_id: str, *, actor: str = "human") -> dict:
        return {"branch_id": branch_id,
                **self._emit("branch_merged", actor=actor, target=[branch_id],
                             payload={"branch_id": branch_id})}

    def prune_branch(self, branch_id: str, *, actor: str = "human", reason: str = "",
                     node_ids: list[str] | None = None) -> dict:
        for nid in (node_ids or []):
            self.set_work_state(nid, "archived", actor=actor, reason=reason)
        return {"branch_id": branch_id,
                **self._emit("branch_pruned", actor=actor, target=[branch_id],
                             payload={"branch_id": branch_id, "reason": reason,
                                      "node_ids": list(node_ids or [])})}

    def reopen(self, node_id: str, *, actor: str = "human", reason: str = "",
               to_state: str = "proposed") -> dict:
        """M6 Reopen：显式事件，不静默改写历史状态。"""
        ev = self.set_work_state(node_id, to_state, actor=actor, reopen=True, reason=reason)
        self._emit("question_reopened", actor=actor, target=[node_id],
                   payload={"node_id": node_id, "reason": reason})
        return ev

    # ------------------------------------------------------------ 影响报告（M5）
    def impact(self, changed: dict[str, str], *, actor: str = "system") -> dict:
        report = propagate(self.graph, changed)
        self._emit("impact_report_generated", actor=actor,
                   target=sorted(changed), payload=report)
        # H-DEP-002：报告携带的状态离场*提议*写入日志（proposed_only，不改变当前状态；
        # 执行需 human_approval_granted + 显式转换事件）
        for entry in report["propagated"]:
            proposal = entry.get("proposed_state_change")
            if not proposal:
                continue
            node = self.graph.get(entry["node"])
            if node is None or node.get("proposition_state") == proposal["to"]:
                continue
            self._emit(
                "proposition_state_changed", actor=actor, target=[entry["node"]],
                payload={
                    "from": node["proposition_state"], "to": proposal["to"],
                    "justification": {"route": "refutation",
                                      "assumptions": node.get("assumptions", []),
                                      "note": "依赖影响报告提议（H-DEP-002，待人类批准）"},
                    "proposed_only": True,
                },
            )
        return report

    # ------------------------------------------------------------ 人类授权（原则 9/10）
    def approve(self, event_id: str, *, note: str = "", actor: str = "human") -> dict:
        if actor != "human":
            raise IllegalTransition("人类授权必须由 human actor 签署（原则 9/10）")
        ev = self.log.get(event_id)
        if ev is None:
            raise RDEError(f"被授权的事件不存在: {event_id}")
        return self._emit("human_approval_granted", actor=actor, target=[event_id],
                          payload={"approves": event_id, "note": note})
