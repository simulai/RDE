"""依赖影响传播（Task 5，docs/dependency_propagation.md）。

核心规则（验收标准 4/5/10）：
- 单条推导路线失效 ≠ 结论失效：按证明路线聚合判定；
- still_valid 只表示"尚有未被本次变化命中的路线"，action 固定为 review_routes，
  不得自动升级为已验证（原则 10、边界 8）；
- 元数据缺失 → unjudgeable（显式报告无法判断，验收标准 10）。

H-DEP-001（独立性判定）与 H-DEP-002（提议 vs 执行）均为待验证假说。
"""

from __future__ import annotations

from ..errors import DependencyError
from ..graph import EVIDENTIAL_TYPES, BLOCKING_TYPES, downstream_of

#: 基础节点变化类型
CHANGE_KINDS = frozenset({"modified", "refuted", "withdrawn", "superseded"})


def _route_status(route: dict, graph, delta: set[str]) -> str:
    """评估单条推导路线：intact | broken | unknown。

    规则（H-DEP-001 的当前操作化，开放问题 Q-DEP-001）：
    - 前提直接处于变化集 Δ → broken；
    - 假设前提被推翻（false_in_scope）或归档 → broken；（默认 unknown 的假设是被“姑且承认”的，
      不因语义未判定而判死路线——假设的本职就是被假定）
    - 命题前提为 false_in_scope / not_applicable → broken；命题前提仍为 unknown/underdetermined → unknown
      （前提本身未证，不能说路线完好，也不能说失效）；
    - 定义前提被归档 → broken；被取代（superseded） → unknown（需按版本复核，不默认完好）；
    - 推导前提被 invalidated → broken；前提元数据缺失 → unknown（不默认完好）。
    """
    premises = route.get("premises")
    # 路线自身被撤销 → 直接 broken（F-C7 审计修复：此前只检查前提中的 derivation，
    # 忽略了路线自身 status=invalidated）
    if route.get("status") == "invalidated":
        return "broken"
    if not premises:
        # 回退到 derived_from 边索引；若仍无前提元数据 → unknown
        premises = [
            pid for e in graph.active_edges()
            if e["type"] == "derived_from" and route["id"] in e.get("premises", [])
            for pid in e.get("conclusions", [])
        ]
        if not premises:
            return "unknown"
    status = "intact"
    for pid in premises:
        if pid in delta:
            return "broken"
        pnode = graph.get(pid)
        if pnode is None:
            return "unknown"          # 前提缺失 → 不能默认完好（Q-DEP-001 缓解）
        ptype = pnode.get("type")
        pstate = pnode.get("proposition_state")
        wstate = pnode.get("work_state")
        if ptype in ("assumption", "definition") and wstate in ("archived",):
            return "broken"
        if ptype == "assumption":
            if pstate == "false_in_scope":
                return "broken"
            continue                   # 其余状态：假设被姑且承认
        if ptype == "claim":
            if pstate in ("false_in_scope", "not_applicable"):
                return "broken"
            if pstate != "true_in_scope":
                status = "unknown" if status == "intact" else status
        if ptype == "definition":
            if wstate == "superseded":
                status = "unknown" if status == "intact" else status
        if ptype == "derivation" and pnode.get("status") == "invalidated":
            return "broken"
    return status


def _classify_claim(claim: dict, graph, delta: set[str]) -> dict:
    routes = graph.derivations_for(claim["id"])
    if not routes:
        return {
            "node": claim["id"], "kind": "claim",
            "status": "unjudgeable",
            "reason": "缺少推导路线元数据（routes/derived_from 均为空）",
            "action": "collect_metadata",
            "routes_broken": [], "routes_intact": [],
        }
    broken, intact, unknown = [], [], []
    for d in sorted(routes, key=lambda r: r["id"]):
        st = _route_status(d, graph, delta)
        {"broken": broken, "intact": intact, "unknown": unknown}[st].append(d["id"])
    base = {"node": claim["id"], "kind": "claim",
            "routes_broken": broken, "routes_intact": intact}
    if intact:
        # 验收标准 5：单条路线失效不会错误地自动推翻所有其他路线
        return {**base, "status": "still_valid", "action": "review_routes",
                "note": "仍有未被本次变化命中的路线；不构成已验证（原则 10）"}
    if unknown and not broken:
        return {**base, "status": "unjudgeable",
                "reason": f"路线前提元数据不完整: {unknown}",
                "action": "collect_metadata"}
    if unknown and broken:
        return {**base, "status": "unjudgeable",
                "reason": f"部分路线失效({broken})、其余前提元数据不完整({unknown})，无法判定",
                "action": "collect_metadata"}
    # 全部路线失效
    return {**base, "status": "under_review", "action": "recheck_required"}


def propagate(graph, changed: dict[str, str]) -> dict:
    """计算基础节点变化的下游影响报告。

    changed: {node_id: kind}，kind ∈ CHANGE_KINDS。
    返回 event_sourcing/dependency_propagation 文档定义的报告结构。
    """
    if not isinstance(changed, dict) or not changed:
        raise DependencyError("changed 必须是非空 dict: {node_id: kind}")
    for node_id, kind in changed.items():
        if kind not in CHANGE_KINDS:
            raise DependencyError(f"未知变化类型 {kind!r}（node={node_id}）")
        if graph.get(node_id) is None:
            raise DependencyError(f"变化节点不存在于图中: {node_id}")

    delta = set(changed)
    direct = []
    propagated = []
    still_valid = []
    route_stopped = []
    unjudgeable = []
    evidence_conclusions = []

    # Step 1-2: 下游可达（带第一条命中的关系类型用于分类；含节点字段的隐式结构关系）
    idx = graph.structure_indexes()
    frontier = sorted(delta)
    visited: set[str] = set(delta)
    first_edge_kind: dict[str, str] = {}
    while frontier:
        current = frontier.pop(0)
        neighbors: list[tuple[str, str]] = list(graph.implicit_downstream(current, idx))
        for e in sorted(graph.active_edges(), key=lambda x: x["id"]):
            for nxt in downstream_of(e, current):
                neighbors.append((nxt, e["type"]))
        for nxt, via in neighbors:
            if nxt not in first_edge_kind:
                first_edge_kind[nxt] = via
            if nxt not in visited:
                visited.add(nxt)
                frontier.append(nxt)

    reached = sorted(visited - delta)
    for nid in reached:
        node = graph.get(nid)
        if node is None:
            unjudgeable.append({"node": nid, "reason": "下游引用的节点不在图中"})
            continue
        direct.append(nid)
        ntype = node.get("type")
        hit_kind = first_edge_kind.get(nid, "")

        # --- 证据维度路径：证据类边 → 重新解释，不触碰语义状态
        if hit_kind in EVIDENTIAL_TYPES or ntype in ("evidence", "experiment"):
            entry = {"node": nid, "kind": "evidence_conclusion",
                     "status": "needs_interpretation",
                     "action": "reinterpret", "via": hit_kind}
            propagated.append(entry)
            evidence_conclusions.append(nid)
            continue

        # --- 阻塞路径：研究路线停止
        if hit_kind in BLOCKING_TYPES:
            propagated.append({"node": nid, "kind": "managerial",
                               "status": "route_stopped", "action": "review_route",
                               "via": hit_kind})
            route_stopped.append(nid)
            continue

        # --- 命题：证明路线聚合（核心规则）
        if ntype == "claim":
            entry = _classify_claim(node, graph, delta)
            entry["via"] = hit_kind
            if entry["status"] == "still_valid":
                still_valid.append(nid)
            elif entry["status"] == "unjudgeable":
                unjudgeable.append({"node": nid, "reason": entry.get("reason", "")})
            elif entry["status"] == "under_review":
                # H-DEP-002：推翻类变化只生成*提议*状态离场，不自动执行
                if any(k == "refuted" for k in changed.values()):
                    entry["proposed_state_change"] = {
                        "to": "unknown", "proposed_only": True,
                        "requires": "human_approval_granted",
                    }
            propagated.append(entry)
            continue

        # --- 推导路线本身
        if ntype == "derivation":
            status = "broken" if any(
                p in delta for p in node.get("premises", [])
            ) else "affected"
            propagated.append({"node": nid, "kind": "derivation",
                               "status": status, "action": "recheck_route",
                               "via": hit_kind})
            continue

        # --- 其他类型：进入复核集；类型未知 → unjudgeable
        if ntype in ("question", "decision", "project"):
            propagated.append({"node": nid, "kind": "managerial",
                               "status": "needs_review", "action": "review", "via": hit_kind})
        elif ntype in ("definition", "assumption", "artifact", "version", "event"):
            propagated.append({"node": nid, "kind": "structural",
                               "status": "needs_review", "action": "review", "via": hit_kind})
        else:
            unjudgeable.append({"node": nid, "reason": f"未知节点类型 {ntype!r}"})
            propagated.append({"node": nid, "kind": "unknown",
                               "status": "unjudgeable", "action": "collect_metadata"})

    if len(changed) == 1:
        (single_node, single_kind), = changed.items()
        change = {"node": single_node, "kind": single_kind}
    else:
        change = {"node": sorted(delta), "kind": "modified"}
    report = {
        "change": change,
        "directly_affected": direct,
        "propagated": propagated,
        "still_valid": sorted(still_valid),
        "route_stopped": sorted(route_stopped),
        "unjudgeable": sorted(unjudgeable, key=lambda u: u["node"]),
    }
    return report


def impact_report(graph, changed: dict[str, str]) -> dict:
    """同 propagate；命名对应事件 impact_report_generated 的 payload。"""
    return propagate(graph, changed)
