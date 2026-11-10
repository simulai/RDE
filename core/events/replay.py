"""事件重放：KnowledgeState = fold(replay, initial, events)（docs/event_sourcing.md §4）。

确定性要求：
- 排序只依赖 seq；
- handler 不读时钟/随机数/外部状态；
- 未知事件类型 → ReplayError（不静默跳过）；
- 重放时重新执行状态机校验（日志本身也必须合法）。

重放同时是第二重校验：任何绕过状态机写入的非法历史在重放时会失败。
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Iterable

from ..errors import ReplayError
from .. import state_machine as sm
from ..events import canonical


def empty_state() -> dict:
    return {
        "nodes": {},        # id -> node（当前版本）
        "edges": {},        # id -> edge
        "history": {},      # node_id -> [被取代的旧版本节点快照]
        "decisions": {},    # node_id -> decision record
        "reports": [],      # impact reports
        "branches": {},     # branch_id -> {status, ...}
        "forks": [],        # fork records
        "superseded_pairs": [],
        "proposals": [],    # proposed_only 的状态变更建议（H-DEP-002）
        "approvals": [],    # human_approval_granted
        "reopened": [],
        "checkpoints": [],
    }


def _node(state: dict, node_id: str) -> dict:
    node = state["nodes"].get(node_id)
    if node is None:
        raise ReplayError(f"事件引用了不存在的节点: {node_id}")
    return node


def _require_target(ev: dict) -> str:
    if not ev.get("target"):
        raise ReplayError(f"事件 {ev.get('event_id')} 缺少 target")
    return ev["target"][0]


# ------------------------------------------------------------------ handlers

def _node_created(state: dict, ev: dict) -> None:
    node = copy.deepcopy(ev["payload"]["node"])
    if node["id"] in state["nodes"]:
        raise ReplayError(f"重复创建节点: {node['id']}（事件溯源不允许覆盖）")
    state["nodes"][node["id"]] = node


def _node_version_created(state: dict, ev: dict) -> None:
    node = copy.deepcopy(ev["payload"]["node"])
    old = _node(state, node["id"])
    if node["version"] <= old["version"]:
        raise ReplayError(f"版本回退: {node['id']} v{old['version']} → v{node['version']}")
    state["history"].setdefault(node["id"], []).append(old)
    state["nodes"][node["id"]] = node


def _edge_created(state: dict, ev: dict) -> None:
    edge = copy.deepcopy(ev["payload"]["edge"])
    if edge["id"] in state["edges"]:
        raise ReplayError(f"重复创建边: {edge['id']}")
    state["edges"][edge["id"]] = edge


def _edge_validity_changed(state: dict, ev: dict) -> None:
    p = ev["payload"]
    edge = state["edges"].get(p["edge_id"])
    if edge is None:
        raise ReplayError(f"edge_validity_changed 引用不存在的边: {p['edge_id']}")
    edge["validity"] = p["validity"]


def _proposition_state_changed(state: dict, ev: dict) -> None:
    node_id = _require_target(ev)
    node = _node(state, node_id)
    p = ev["payload"]
    if p.get("proposed_only"):
        state["proposals"].append({**p, "node_id": node_id, "seq": ev["seq"]})
        return
    sm.check_proposition_transition(
        p["from"], p["to"],
        justification=p.get("justification"),
        scope=node.get("scope"),
    )
    if node.get("proposition_state") != p["from"]:
        raise ReplayError(f"{node_id} 命题状态与事件 from 不一致")
    node["proposition_state"] = p["to"]


def _evidence_state_changed(state: dict, ev: dict) -> None:
    node_id = _require_target(ev)
    node = _node(state, node_id)
    p = ev["payload"]
    sm.check_evidence_transition(p["from"], p["to"], driven_by=p.get("driven_by"))
    if node.get("evidence_state") != p["from"]:
        raise ReplayError(f"{node_id} 证据状态与事件 from 不一致")
    node["evidence_state"] = p["to"]


def _work_state_changed(state: dict, ev: dict) -> None:
    node_id = _require_target(ev)
    node = _node(state, node_id)
    p = ev["payload"]
    sm.check_work_transition(p["from"], p["to"], reopen=bool(p.get("reopen")))
    if node.get("work_state") != p["from"]:
        raise ReplayError(f"{node_id} 工作状态与事件 from 不一致")
    node["work_state"] = p["to"]


def _evidence_appended(state: dict, ev: dict) -> None:
    node = copy.deepcopy(ev["payload"]["evidence"])
    if node.get("type") != "evidence":
        raise ReplayError("evidence_appended 的 payload 必须是 evidence 节点")
    _node_created(state, {**ev, "payload": {"node": node}})
    # 派生缓存：current_evidence 由事件决定（同一日志 → 同一状态，验收标准 1）
    for claim_id in sorted(set(node.get("supports", [])) | set(node.get("contradicts", []))):
        claim = state["nodes"].get(claim_id)
        if claim is None:
            raise ReplayError(f"证据 {node['id']} 引用了不存在的命题 {claim_id}")
        lst = claim.setdefault("current_evidence", [])
        if node["id"] not in lst:
            lst.append(node["id"])
            lst.sort()


def _evidence_invalidated(state: dict, ev: dict) -> None:
    p = ev["payload"]
    node = _node(state, p["evidence_id"])
    if node.get("type") != "evidence":
        raise ReplayError("evidence_invalidated 的对象不是 evidence 节点")
    node["validity"] = "invalidated"
    node["invalidation"] = {
        "reason": p.get("reason", ""),
        "actor": ev["actor"],
        "seq": ev["seq"],
    }


def _evidence_withdrawn(state: dict, ev: dict) -> None:
    p = ev["payload"]
    node = _node(state, p["evidence_id"])
    node["validity"] = "withdrawn"
    node["invalidation"] = {"reason": p.get("reason", ""), "actor": ev["actor"], "seq": ev["seq"]}


def _derivation_started(state: dict, ev: dict) -> None:
    node = copy.deepcopy(ev["payload"]["derivation"])
    if node.get("type") != "derivation":
        raise ReplayError("derivation_started 的 payload 必须是 derivation 节点")
    _node_created(state, {**ev, "payload": {"node": node}})


def _derivation_status(state: dict, ev: dict, status: str) -> None:
    node_id = _require_target(ev)
    node = _node(state, node_id)
    if node.get("type") != "derivation":
        raise ReplayError(f"{ev['type']} 的对象不是 derivation: {node_id}")
    node["status"] = status


def _derivation_completed(state: dict, ev: dict) -> None:
    _derivation_status(state, ev, "completed")


def _derivation_invalidated(state: dict, ev: dict) -> None:
    _derivation_status(state, ev, "invalidated")


def _impact_report_generated(state: dict, ev: dict) -> None:
    state["reports"].append(copy.deepcopy(ev["payload"]))


def _decision_recorded(state: dict, ev: dict) -> None:
    node_id = _require_target(ev)
    _node(state, node_id)
    state["decisions"][node_id] = copy.deepcopy(ev["payload"]["decision"])


def _human_approval_granted(state: dict, ev: dict) -> None:
    state["approvals"].append(copy.deepcopy(ev["payload"]))


def _branch_event(state: dict, ev: dict, status: str) -> None:
    p = ev["payload"]
    bid = p["branch_id"]
    entry = state["branches"].setdefault(bid, {"status": "open", "history": []})
    entry["status"] = status
    entry["history"].append({"seq": ev["seq"], "status": status, **{k: v for k, v in p.items() if k != "branch_id"}})


def _branch_created(state: dict, ev: dict) -> None:
    _branch_event(state, ev, "open")


def _branch_merged(state: dict, ev: dict) -> None:
    _branch_event(state, ev, "merged")


def _branch_pruned(state: dict, ev: dict) -> None:
    _branch_event(state, ev, "pruned")


def _question_reopened(state: dict, ev: dict) -> None:
    state["reopened"].append({"node_id": ev["target"][0], "seq": ev["seq"]})


def _fork_created(state: dict, ev: dict) -> None:
    state["forks"].append(copy.deepcopy(ev["payload"]))


def _superseded(state: dict, ev: dict) -> None:
    state["superseded_pairs"].append(copy.deepcopy(ev["payload"]))


def _replay_checkpoint(state: dict, ev: dict) -> None:
    state["checkpoints"].append(copy.deepcopy(ev["payload"]))


def _north_star_modified(state: dict, ev: dict) -> None:
    # 第一阶段禁令（任务书 §12）：北极星修改仅 schema 预留，重放时显式失败。
    raise ReplayError("第一阶段禁止 north_star_modified 事件（需人类授权的未来能力）")


HANDLERS = {
    "node_created": _node_created,
    "node_version_created": _node_version_created,
    "edge_created": _edge_created,
    "edge_validity_changed": _edge_validity_changed,
    "proposition_state_changed": _proposition_state_changed,
    "evidence_state_changed": _evidence_state_changed,
    "work_state_changed": _work_state_changed,
    "evidence_appended": _evidence_appended,
    "evidence_invalidated": _evidence_invalidated,
    "evidence_withdrawn": _evidence_withdrawn,
    "derivation_started": _derivation_started,
    "derivation_completed": _derivation_completed,
    "derivation_invalidated": _derivation_invalidated,
    "impact_report_generated": _impact_report_generated,
    "decision_recorded": _decision_recorded,
    "human_approval_granted": _human_approval_granted,
    "branch_created": _branch_created,
    "branch_merged": _branch_merged,
    "branch_pruned": _branch_pruned,
    "question_reopened": _question_reopened,
    "fork_created": _fork_created,
    "superseded": _superseded,
    "replay_checkpoint": _replay_checkpoint,
    "north_star_modified": _north_star_modified,
}


def apply(state: dict, ev: dict) -> dict:
    handler = HANDLERS.get(ev["type"])
    if handler is None:
        raise ReplayError(f"未知事件类型: {ev['type']}（禁止静默跳过历史）")
    handler(state, ev)
    return state


def replay(events: Iterable[dict], upto: int | None = None) -> dict:
    """从事件序列重建知识状态。seq 升序；upto 用于时间点重建（验收标准 2）。"""
    ordered = sorted(events, key=lambda e: e["seq"])
    state = empty_state()
    for i, ev in enumerate(ordered):
        if ev["seq"] != i:
            raise ReplayError(f"事件 seq 不连续: 期望 {i}, 实际 {ev['seq']}")
        if upto is not None and ev["seq"] > upto:
            break
        apply(state, ev)
    return state


def state_digest(state: dict) -> str:
    """知识状态摘要：只覆盖当前节点与边（按 ID 排序，字节级确定）。"""
    basis = {
        "nodes": {k: state["nodes"][k] for k in sorted(state["nodes"])},
        "edges": {k: state["edges"][k] for k in sorted(state["edges"])},
    }
    return hashlib.sha256(canonical(basis).encode("utf-8")).hexdigest()
