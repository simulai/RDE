"""研究知识超图读模型（docs/graph_semantics.md）。

读模型可通过事件重放构建，也可为结构分析目的直接构建（tests）。
生产路径中任何写入都必须先经过 engine 产生事件（架构 L1 = 唯一真相源）。

边方向约定（premises → conclusions）：
- entails/supports/contradicts/tests/instantiates/refines/motivates/blocks:
    premises 是上游（前提/证据/阻塞源），conclusions 是下游。
- depends_on: premises = 依赖者（下游），conclusions = 被依赖基础节点（上游）。
- derived_from: premises = 结果（下游），conclusions = 来源（上游）。
- supersedes: premises = 新版本（下游方向的新对象），conclusions = 旧版本。
"""

from __future__ import annotations

from typing import Iterable

from ..errors import ValidationError

#: 边类别与类型的一致性（graph_semantics §3；与 edge.schema.json 对应）
CATEGORY_BY_TYPE: dict[str, str] = {
    "depends_on": "logical",
    "entails": "logical",
    "supports": "evidential",
    "contradicts": "evidential",
    "tests": "evidential",
    "instantiates": "structural",
    "refines": "structural",
    "supersedes": "structural",
    "motivates": "managerial",
    "blocks": "managerial",
    "derived_from": "managerial",
}

#: 从上游（base）沿传播方向走到下游的边类型（正向）
_FORWARD_TYPES = frozenset({
    "entails", "supports", "contradicts", "tests",
    "instantiates", "refines", "motivates", "blocks",
})
#: 从下游对象回溯到上游时为正向、但对基础节点变化需要『反向』传播的类型
_REVERSE_TYPES = frozenset({"depends_on", "derived_from", "supersedes"})

#: 证据类边：跨过这类边到达的结论标记为『需重新解释』而非逻辑影响
EVIDENTIAL_TYPES = frozenset({"supports", "contradicts", "tests"})
#: 管理类边中的阻塞
BLOCKING_TYPES = frozenset({"blocks"})


def downstream_of(edge: dict, current: str) -> list[str]:
    """若 current 是该边的上游端，返回其下游节点；否则返回空。"""
    etype = edge["type"]
    premises = edge.get("premises", [])
    conclusions = edge.get("conclusions", [])
    if etype in _FORWARD_TYPES and current in premises:
        return list(conclusions)
    if etype in _REVERSE_TYPES and current in conclusions:
        return list(premises)
    return []


def upstream_of(edge: dict, current: str) -> list[str]:
    """downstream_of 的对偶：current 为下游时返回上游。"""
    etype = edge["type"]
    premises = edge.get("premises", [])
    conclusions = edge.get("conclusions", [])
    if etype in _FORWARD_TYPES and current in conclusions:
        return list(premises)
    if etype in _REVERSE_TYPES and current in premises:
        return list(conclusions)
    return []


def validate_edge(edge: dict) -> None:
    """边的最低结构与类别一致性校验（严格语义的第一道闸）。"""
    for field in ("id", "type", "premises", "conclusions", "category", "validity"):
        if field not in edge:
            raise ValidationError(f"边缺少字段 {field}: {edge.get('id')}")
    etype = edge["type"]
    if etype not in CATEGORY_BY_TYPE:
        raise ValidationError(f"未知边类型: {etype}")
    if edge["category"] != CATEGORY_BY_TYPE[etype]:
        raise ValidationError(
            f"边 {edge['id']} 类别不一致: {etype} 应为 {CATEGORY_BY_TYPE[etype]}，"
            f"实际 {edge['category']}（逻辑/证据/管理语义不得混用）"
        )
    if not edge["premises"] or not edge["conclusions"]:
        raise ValidationError(f"超边 {edge['id']} 前提与结论均不可为空")
    if len(set(edge["premises"])) != len(edge["premises"]):
        raise ValidationError(f"超边 {edge['id']} premises 重复")
    if len(set(edge["conclusions"])) != len(edge["conclusions"]):
        raise ValidationError(f"超边 {edge['id']} conclusions 重复")


def validate_node(node: dict) -> None:
    for field in ("id", "type", "version", "created_at", "source", "scope"):
        if field not in node:
            raise ValidationError(f"节点缺少字段 {field}: {node.get('id')}")
    if not isinstance(node["version"], int) or node["version"] < 1:
        raise ValidationError(f"节点 {node['id']} 版本必须是 ≥1 的整数")
    if node["type"] == "claim":
        for f in (
            "content", "definition_versions", "assumptions", "dependency_nodes",
            "proof_obligations", "falsification_conditions", "current_evidence",
            "proposition_state", "evidence_state", "work_state", "next_research_action",
        ):
            if f not in node:
                raise ValidationError(f"Claim {node['id']} 缺少字段 {f}（schemas/claim.schema.json）")
    if node["type"] == "evidence":
        for f in ("content", "evidence_kind", "validity"):
            if f not in node:
                raise ValidationError(f"Evidence {node['id']} 缺少字段 {f}（schemas/evidence.schema.json）")
    if node["type"] == "derivation":
        for f in ("content", "premises", "concludes", "track"):
            if f not in node:
                raise ValidationError(f"Derivation {node['id']} 缺少字段 {f}")

    # F-E02/F-E03（原则 4/L1 与 state_semantics L3）：状态机的绑定与义务约束必须
    # 在*所有*入口生效 —— 否则可绕过 set_proposition_state/set_work_state 直接携带。
    if node.get("type") == "claim" and node.get("work_state") == "completed":
        obligations = node.get("proof_obligations") or []
        if not obligations:
            raise ValidationError("L3: Claim 缺少证明义务记录，不得以 completed 创建")
        open_ids = [o.get("id") for o in obligations
                    if o.get("status") not in ("discharged", "withdrawn")]
        if open_ids:
            raise ValidationError(
                f"L3: 证明义务未完成 {open_ids}，不得以 completed 创建（state_semantics L3）"
            )
    if node.get("proposition_state") in ("true_in_scope", "false_in_scope"):
        if not node.get("assumptions"):
            raise ValidationError(
                "truth state 绑定缺失: 携带 true/false_in_scope 必须绑定假设集合"
                "（原则 4/L1；创建入口与转换入口同样检查）"
            )
        if not node.get("scope"):
            raise ValidationError(
                "truth state 绑定缺失: 必须绑定非空适用范围 scope（原则 4/L1）"
            )


class ResearchGraph:
    """超图读模型：查询、遍历、路线索引。"""

    def __init__(self, state: dict | None = None):
        if state is not None:
            self.nodes: dict[str, dict] = state["nodes"]
            self.edges: dict[str, dict] = state["edges"]
        else:
            self.nodes = {}
            self.edges = {}

    # ------------------------------------------------------------- 基本读写
    def add_node(self, node: dict) -> dict:
        validate_node(node)
        if node["id"] in self.nodes:
            raise ValidationError(f"节点已存在: {node['id']}")
        self.nodes[node["id"]] = node
        return node

    def add_edge(self, edge: dict) -> dict:
        validate_edge(edge)
        if edge["id"] in self.edges:
            raise ValidationError(f"边已存在: {edge['id']}")
        self.edges[edge["id"]] = edge
        return edge

    def get(self, node_id: str) -> dict | None:
        return self.nodes.get(node_id)

    def require(self, node_id: str) -> dict:
        node = self.nodes.get(node_id)
        if node is None:
            raise ValidationError(f"节点不存在: {node_id}")
        return node

    def get_edge(self, edge_id: str) -> dict | None:
        return self.edges.get(edge_id)

    def nodes_of_type(self, type: str) -> list[dict]:
        return sorted((n for n in self.nodes.values() if n["type"] == type), key=lambda n: n["id"])

    def active_edges(self) -> list[dict]:
        return [e for e in self.edges.values() if e.get("validity") == "active"]

    # ------------------------------------------------------------- 遍历
    def structure_indexes(self) -> dict:
        """节点字段承载的隐式结构关系索引（每次调用重建，保证与可变状态一致）。

        - deriv_by_premise: 假设/定义 → 以其为前提的 derivation
        - claims_by_dep:    基础节点 → 依赖它（dependency_nodes/assumptions/definition_versions）的 claim
        """
        deriv_by_premise: dict[str, list[str]] = {}
        for d in self.nodes_of_type("derivation"):
            for p in d.get("premises", []):
                deriv_by_premise.setdefault(p, []).append(d["id"])
        claims_by_dep: dict[str, list[str]] = {}
        for c in self.nodes_of_type("claim"):
            deps = set(c.get("dependency_nodes", []))
            deps |= {a.get("id") for a in c.get("assumptions", []) if a.get("id")}
            deps |= {v.get("id") for v in c.get("definition_versions", []) if v.get("id")}
            for dep in deps:
                claims_by_dep.setdefault(dep, []).append(c["id"])
        return {
            "deriv_by_premise": {k: sorted(v) for k, v in deriv_by_premise.items()},
            "claims_by_dep": {k: sorted(v) for k, v in claims_by_dep.items()},
        }

    def implicit_downstream(self, current: str, idx: dict | None = None) -> list[tuple[str, str]]:
        """节点字段（非显式边）表达的下游关系：[(node_id, via)]，确定性排序。"""
        idx = idx if idx is not None else self.structure_indexes()
        out: list[tuple[str, str]] = []
        for did in idx["deriv_by_premise"].get(current, []):
            out.append((did, "derived_from"))
        for cid in idx["claims_by_dep"].get(current, []):
            out.append((cid, "depends_on"))
        node = self.nodes.get(current)
        if node is not None:
            if node.get("type") == "derivation":
                for cid in node.get("concludes", []):
                    out.append((cid, "derived_from"))
            elif node.get("type") == "evidence":
                for cid in sorted(set(node.get("supports", [])) | set(node.get("contradicts", []))):
                    out.append((cid, "supports" if cid in node.get("supports", []) else "contradicts"))
            # 注：不把 claim → routes(derivation) 视为下游 —— 路线是命题的*上游*来源，
            # 反向遍历会把同级（sibling）路线误报为受影响（见 test_downstream_impact_report）。
        return out

    def downstream(self, start: Iterable[str], *, include_inactive: bool = False) -> list[str]:
        """沿传播方向的可达节点集合（不含起点），按 ID 排序保证确定性。含隐式结构关系。"""
        edges = self.active_edges() if not include_inactive else list(self.edges.values())
        idx = self.structure_indexes()
        start_set = set(start)
        seen: set[str] = set()
        frontier = list(start_set)
        while frontier:
            current = frontier.pop(0)
            neighbors: list[tuple[str, str]] = list(self.implicit_downstream(current, idx))
            for e in edges:
                for nxt in downstream_of(e, current):
                    neighbors.append((nxt, e["type"]))
            for nxt, _via in neighbors:
                if nxt not in seen and nxt not in start_set:
                    seen.add(nxt)
                    frontier.append(nxt)
        return sorted(seen)

    def upstream(self, start: Iterable[str], *, include_inactive: bool = False) -> list[str]:
        edges = self.active_edges() if not include_inactive else list(self.edges.values())
        seen: set[str] = set()
        frontier = list(start)
        while frontier:
            current = frontier.pop(0)
            for e in edges:
                for prev in upstream_of(e, current):
                    if prev not in seen and prev not in start:
                        seen.add(prev)
                        frontier.append(prev)
        return sorted(seen)

    def incoming(self, node_id: str) -> list[dict]:
        return sorted(
            [e for e in self.active_edges() if node_id in e.get("conclusions", []) or node_id in e.get("premises", [])],
            key=lambda e: e["id"],
        )

    # ------------------------------------------------------------- 路线/证据索引
    def derivations_for(self, claim_id: str) -> list[dict]:
        """得出该命题的推导路线（按 ID 排序）。同时索引 node.routes 字段与 concludes 字段。"""
        routes = []
        claim = self.nodes.get(claim_id)
        declared = set(claim.get("routes", [])) if claim else set()
        for n in self.nodes_of_type("derivation"):
            if claim_id in n.get("concludes", []) or n["id"] in declared:
                routes.append(n)
        return routes

    def evidence_touching(self, claim_id: str) -> list[dict]:
        out = []
        for e in self.nodes_of_type("evidence"):
            if claim_id in e.get("supports", []) or claim_id in e.get("contradicts", []):
                out.append(e)
        return out

    def claims_supported_by(self, evidence_id: str) -> list[str]:
        ev = self.require(evidence_id)
        return sorted(set(ev.get("supports", [])))

    def claims_contradicted_by(self, evidence_id: str) -> list[str]:
        ev = self.require(evidence_id)
        return sorted(set(ev.get("contradicts", [])))

    def derived_from_edges(self, node_id: str) -> list[dict]:
        """node_id 作为来源端的 derived_from 边（即 derived_from 的 premises 是结果）。"""
        return [e for e in self.active_edges() if e["type"] == "derived_from" and node_id in e.get("conclusions", [])]
