"""对抗审计 C — 多证明路线语义（docs/dependency_propagation.md、验收标准 4/5/10）。

设计锚点：
- 单路线失效 ≠ 结论失效（验收标准 5）
- still_valid ≠ 已验证：action 固定 review_routes，不得自动获得正确性（原则 10）
- 元数据缺失 → unjudgeable，不猜测（验收标准 10）
- H-DEP-001/Q-007：路线独立性 = 按声明的前提集 —— 隐藏前提是已知开放问题

发现编号见 reports/adversarial_audit.md（F-Cxx）。
"""

from __future__ import annotations

import pytest

from core import RDE

from conftest import base_node, claim, derivation


def _entry(report: dict, node_id: str) -> dict:
    for e in report["propagated"]:
        if e["node"] == node_id:
            return e
    raise AssertionError(f"{node_id} 不在报告中: {report['propagated']}")


@pytest.fixture()
def two_routes(rde: RDE) -> RDE:
    """两条真正不共享前提的路线支撑 claim-c1；单路线 claim-c2。"""
    for nid, t in (("definition-d1", "definition"), ("definition-d2", "definition"),
                   ("assumption-a1", "assumption"), ("assumption-a2", "assumption")):
        rde.create_node(base_node(nid, t, scope="全局" if t == "definition" else "示例范围",
                                  work="active"))
    rde.create_node(claim("claim-c1", ["derivation-d1", "derivation-d2"],
                          ["definition-d1"], ["assumption-a1"]))
    rde.create_node(claim("claim-c2", ["derivation-d3"], ["definition-d1"], ["assumption-a1"]))
    rde.start_derivation(derivation("derivation-d1", ["assumption-a1", "definition-d1"], ["claim-c1"]))
    rde.start_derivation(derivation("derivation-d2", ["assumption-a2", "definition-d2"], ["claim-c1"]))
    rde.start_derivation(derivation("derivation-d3", ["assumption-a1", "definition-d1"], ["claim-c2"]))
    return rde


# ---------------------------------------------------------------- C1 真独立

def test_c01_truly_independent_routes_bidirectional(two_routes: RDE):
    """推翻任一侧前提，另一侧路线保持 intact；双侧齐推 → under_review。"""
    rep = two_routes.impact({"assumption-a1": "refuted"})
    e = _entry(rep, "claim-c1")
    assert e["routes_broken"] == ["derivation-d1"] and e["routes_intact"] == ["derivation-d2"]
    assert e["status"] == "still_valid" and "claim-c1" in rep["still_valid"]

    rep2 = two_routes.impact({"assumption-a2": "refuted"})
    e2 = _entry(rep2, "claim-c1")
    assert e2["routes_broken"] == ["derivation-d2"] and e2["routes_intact"] == ["derivation-d1"]

    rep3 = two_routes.impact({"assumption-a1": "refuted", "assumption-a2": "refuted"})
    assert _entry(rep3, "claim-c1")["status"] == "under_review"


# ---------------------------------------------------------------- C2 隐藏前提（开放问题 Q-007 的两种表现）

def test_c02a_undeclared_hidden_premise_makes_claim_invisible(two_routes: RDE):
    """F-C2(i)：隐藏前提完全不在任何元数据中 → 命题根本不出现在影响报告里。
    本测试固化该已知限制（不作为正确性证据）：报告的『未列出』不等于『无影响』。
    """
    # 模拟：claim-c3 只在隐藏前提上有真实依赖，但依赖集为空 → 不可达
    two_routes.create_node(claim("claim-c3", [], [], [], work="active"))
    rep = two_routes.impact({"assumption-a1": "refuted"})
    assert "claim-c3" not in rep["directly_affected"]
    # 同时它也不在 unjudgeable —— 完全静默（审计必须据此要求元数据完备性）
    assert not any(u["node"] == "claim-c3" for u in rep["unjudgeable"])


def test_c02b_declared_dependency_but_undeclared_route_premise_false_positive(two_routes: RDE):
    """F-C2(ii)：命题依赖集登记了前提、路线前提未登记 → 路线被判 intact 的假阳性。
    固化当前事实：路线独立性完全取决于元数据诚实性（Q-007/H-DEP-001 的核心风险）。
    """
    # derivation-d2 实际上也依赖 assumption-a1（隐藏），但 premises 只写了 definition-d2
    two_routes.state["nodes"]["derivation-d2"]["premises"] = ["definition-d2"]
    # claim-c1 的依赖集仍登记 a1 → 命题会被波及
    rep = two_routes.impact({"assumption-a1": "refuted"})
    e = _entry(rep, "claim-c1")
    # 假阳性发生：d2 被判 intact → still_valid，尽管它逻辑上依赖被推翻的 a1
    assert e["status"] == "still_valid" and "derivation-d2" in e["routes_intact"]
    assert e["action"] == "review_routes", "设计上必须强制人工复核来兜底此假阳性"
    # 这不是正确性证据 —— 审计结论：报告未列出 ≠ 影响不存在


def test_c03_shared_definition_different_versions_indistinguishable(two_routes: RDE):
    """F-B1/C3：两条路线引用同一定义的不同『版本』——当前模型无法区分。
    前提按 ID 解析 → 两条路线共享同一节点对象。固化该事实（待研究者裁决版本钉住设计）。
    """
    two_routes.start_derivation(derivation("derivation-d1b", ["definition-d1"], ["claim-c1"]))
    two_routes.revise_node("definition-d1", {"content": "v2"}, reason="对抗审计")
    d1 = two_routes.graph.require("derivation-d1")
    d1b = two_routes.graph.require("derivation-d1b")
    # 两条路线都通过同一 ID 引用 definition-d1 → 解析到同一个当前节点（v2），无版本可言
    assert "definition-d1" in d1["premises"] and "definition-d1" in d1b["premises"]
    resolved = two_routes.graph.require("definition-d1")
    assert resolved["version"] == 2, "路线层无法钉住 v1：所有引用者跟随当前版本（F-B1）"


# ---------------------------------------------------------------- C4 元数据不全

def test_c04_broken_plus_unknown_route_is_unjudgeable(two_routes: RDE):
    """一条失效 + 一条元数据不全 → unjudgeable（既不说有效也不说全灭）。"""
    two_routes.state["nodes"]["derivation-d2"]["premises"] = ["missing-node-xyz"]
    rep = two_routes.impact({"assumption-a1": "refuted"})
    e = _entry(rep, "claim-c1")
    assert e["status"] == "unjudgeable"
    assert e["routes_broken"] == ["derivation-d1"] and e["routes_intact"] == []
    assert any(u["node"] == "claim-c1" for u in rep["unjudgeable"])


# ---------------------------------------------------------------- C5 全失效

def test_c05_all_routes_broken_under_review_with_kind_awareness(two_routes: RDE):
    """全失效 → under_review；只有 refuted 类变化才附带*提议*（H-DEP-002），修改不提议。"""
    rep = two_routes.impact({"assumption-a1": "modified"})     # 普通修订
    e = _entry(rep, "claim-c2")
    assert e["status"] == "under_review" and e["action"] == "recheck_required"
    assert "proposed_state_change" not in e, "modified 不应产生语义离场提议"

    rep2 = two_routes.impact({"assumption-a1": "refuted"})     # 推翻
    e2 = _entry(rep2, "claim-c2")
    assert e2["status"] == "under_review"
    assert e2["proposed_state_change"]["proposed_only"] is True
    assert e2["proposed_state_change"]["requires"] == "human_approval_granted"


def test_c06_still_valid_never_grants_correctness(two_routes: RDE):
    """验收标准 5 的另一半：未被命中的路线也*不自动获得正确性*。
    - 命题状态不被改变（无论原来是 unknown 还是 true_in_scope）
    - 不产生任何非 proposed 的语义升级事件
    - action 恒为 review_routes（而非 verified/confirmed）
    """
    # 先按合法路径把 claim-c1 升为 true_in_scope（双路线+绑定）
    two_routes.set_proposition_state(
        "claim-c1", "true_in_scope",
        justification={"route": "mathematical",
                       "assumptions": [{"id": "assumption-a1", "version": 1}]})
    rep = two_routes.impact({"assumption-a1": "refuted"})
    e = _entry(rep, "claim-c1")
    assert e["status"] == "still_valid" and e["action"] == "review_routes"
    # 状态未被改动 —— 既不自动推翻，也不自动维持"已验证"
    assert two_routes.graph.require("claim-c1")["proposition_state"] == "true_in_scope"
    # 影响报告之后，不得新增任何*非提议*的语义状态执行事件
    report_event_seq = two_routes.log.by_type("impact_report_generated")[-1]["seq"]
    new_truth_events = [ev for ev in two_routes.log.by_type("proposition_state_changed")
                        if ev["seq"] > report_event_seq and not ev["payload"].get("proposed_only")]
    assert new_truth_events == [], "影响报告不得自动产生语义状态执行事件"


# ---------------------------------------------------------------- C7 无效推导

def test_c07_invalidated_derivation_breaks_route(two_routes: RDE):
    """被撤销（invalidated）的推导路线必须判 broken。"""
    two_routes.invalidate_derivation("derivation-d2", reason="证明错误被发现")
    rep = two_routes.impact({"assumption-a1": "refuted"})
    e = _entry(rep, "claim-c1")
    # d1 因 a1 失效、d2 因自身 invalidated 失效 → 全灭
    assert e["status"] == "under_review"
    assert set(e["routes_broken"]) == {"derivation-d1", "derivation-d2"}


def test_c08_revoked_derivation_alone_breaks_claim(two_routes: RDE):
    """不需要 Δ：路线自身被撤销后，下次评估即为 broken。"""
    two_routes.invalidate_derivation("derivation-d3", reason="错误")
    from core.dependency_analysis import _route_status
    st = _route_status(two_routes.graph.require("derivation-d3"), two_routes.graph, set())
    assert st == "broken"
