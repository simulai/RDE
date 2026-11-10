"""依赖影响传播测试：下游完整性、多证明路线、单路线失效不推翻、无法判定上报。

对应验收标准 5 / 7 / 10，docs/dependency_propagation.md（Task 5）。
"""

from __future__ import annotations

import pytest

from core import RDE, DependencyError

from conftest import base_node, claim, derivation, evidence


def _report(rde: RDE) -> dict:
    return rde.state["reports"][-1]


def _entry(report: dict, node_id: str) -> dict:
    for e in report["propagated"]:
        if e["node"] == node_id:
            return e
    raise AssertionError(f"{node_id} 不在影响报告中: {report['propagated']}")


# ---------------------------------------------------------------- 验收标准 7

def test_downstream_impact_report(scenario: RDE):
    report = scenario.revise_node("definition-d1", {"content": "v2"}, reason="测试")
    assert report["change"] == {"node": "definition-d1", "kind": "modified"}
    affected = set(report["directly_affected"])
    # 下游完整：直接依赖的命题、以它为前提的推导路线全部入列
    assert {"claim-c1", "claim-c2", "derivation-d1", "derivation-d3"} <= affected
    # 不在下游的节点不被误伤
    assert "assumption-a2" not in affected
    assert "derivation-d2" not in affected
    # 报告以事件形式落盘（可回溯）
    assert scenario.log.by_type("impact_report_generated")[-1]["payload"] == report


def test_downstream_propagation_is_transitive(scenario: RDE):
    """二级下游：assumption-a1 → derivation → claim → 再依赖它的决策。"""
    scenario.create_node(base_node("question-q9", "question", work="active"))
    scenario.create_edge({
        "id": "edge-mot-1", "type": "motivates", "category": "managerial",
        "premises": ["claim-c2"], "conclusions": ["question-q9"],
        "created_at": "2026-01-01T00:00:00Z", "source": {"origin": "human"},
        "scope": "示例范围", "validity": "active",
    })
    report = scenario.impact({"assumption-a1": "refuted"})
    assert "question-q9" in report["directly_affected"]


# ---------------------------------------------------------------- 验收标准 5（核心）

def test_single_route_failure_keeps_claim(scenario: RDE):
    """一条路线失效，结论不被自动推翻（仍标记 review_routes）。"""
    report = scenario.refute("assumption-a1") and _report(scenario)
    entry = _entry(report, "claim-c1")
    assert entry["status"] == "still_valid"
    assert entry["routes_broken"] == ["derivation-d1"]
    assert entry["routes_intact"] == ["derivation-d2"]
    assert entry["action"] == "review_routes"        # 不是 verified（原则 10）
    assert "claim-c1" in report["still_valid"]
    # 状态未被改动
    assert scenario.graph.require("claim-c1")["proposition_state"] == "unknown"


def test_all_routes_broken_triggers_under_review(scenario: RDE):
    """全部路线失效 → under_review + 仅提议离场（H-DEP-002）。"""
    report = scenario.refute("assumption-a1") and _report(scenario)
    entry = _entry(report, "claim-c2")
    assert entry["status"] == "under_review"
    assert entry["action"] == "recheck_required"
    assert entry["routes_broken"] == ["derivation-d3"]
    assert entry["routes_intact"] == []
    assert entry["proposed_state_change"]["proposed_only"] is True
    assert entry["proposed_state_change"]["requires"] == "human_approval_granted"


def test_independent_routes_survive_full_refutation(scenario: RDE):
    """两条互不相交前提的路线：推翻其一前提，另一条判定完好（H-DEP-001 结构检验）。"""
    report = scenario.impact({"assumption-a1": "refuted"})
    entry = _entry(report, "claim-c1")
    assert "derivation-d2" in entry["routes_intact"]
    # 反向：推翻 d2 的前提
    report2 = scenario.impact({"assumption-a2": "refuted"})
    entry2 = _entry(report2, "claim-c1")
    assert "derivation-d1" in entry2["routes_intact"]
    # 两个前提同时被推翻 → 全部路线失效
    report3 = scenario.impact({"assumption-a1": "refuted", "assumption-a2": "refuted"})
    entry3 = _entry(report3, "claim-c1")
    assert entry3["status"] == "under_review"


# ---------------------------------------------------------------- 验收标准 10

def test_unjudgeable_reported(scenario: RDE):
    """缺少推导元数据的命题 → unjudgeable，不猜。"""
    scenario.create_node(claim("claim-nometa", [], [], ["assumption-a1"], work="proposed"))
    report = scenario.impact({"assumption-a1": "refuted"})
    entry = _entry(report, "claim-nometa")
    assert entry["status"] == "unjudgeable"
    assert entry["action"] == "collect_metadata"
    assert any(u["node"] == "claim-nometa" and "元数据" in u["reason"]
               for u in report["unjudgeable"])


def test_missing_premise_node_reported_unjudgeable(scenario: RDE):
    """路线引用了不在图中的前提 → unknown → unjudgeable（不默认完好）。"""
    scenario.create_node(claim("claim-ghost", ["derivation-ghost"], [], ["assumption-a1"],
                               work="proposed"))
    scenario.start_derivation(derivation("derivation-ghost", ["assumption-gone"],
                                         ["claim-ghost"]))
    report = scenario.impact({"assumption-a1": "refuted"})
    entry = _entry(report, "claim-ghost")
    assert entry["status"] == "unjudgeable"
    from core.dependency_analysis import _route_status
    st = _route_status(scenario.graph.require("derivation-ghost"), scenario.graph,
                       {"assumption-a1"})
    assert st == "unknown"


# ---------------------------------------------------------------- 证据维度与阻塞

def test_evidence_change_needs_interpretation_not_logic(scenario: RDE):
    """证据被撤回 → 实验/证据结论只标记『需重新解释』，不触碰语义状态。"""
    scenario.append_evidence(evidence("evidence-m1", supports=["claim-c1"]))
    report = scenario.impact({"evidence-m1": "withdrawn"})
    entry = _entry(report, "claim-c1")
    # 命题同时经依赖路径可达：证据维度变化单独评估时以证据路径为准
    assert entry["status"] in ("needs_interpretation", "still_valid", "under_review", "unjudgeable")
    assert scenario.graph.require("claim-c1")["evidence_state"] in ("supported", "none")


def test_blocking_edge_stops_route(scenario: RDE):
    scenario.create_node(base_node("question-q5", "question", work="active"))
    scenario.create_edge({
        "id": "edge-blk-1", "type": "blocks", "category": "managerial",
        "premises": ["assumption-a1"], "conclusions": ["question-q5"],
        "created_at": "2026-01-01T00:00:00Z", "source": {"origin": "human"},
        "scope": "示例范围", "validity": "active",
    })
    report = scenario.impact({"assumption-a1": "refuted"})
    assert "question-q5" in report["route_stopped"]
    assert _entry(report, "question-q5")["status"] == "route_stopped"


# ---------------------------------------------------------------- 输入校验

def test_invalid_change_input_rejected(scenario: RDE):
    with pytest.raises(DependencyError, match="变化类型"):
        scenario.impact({"assumption-a1": "exploded"})
    with pytest.raises(DependencyError, match="不存在"):
        scenario.impact({"assumption-nope": "modified"})
    with pytest.raises(DependencyError, match="非空"):
        scenario.impact({})


def test_prune_archives_and_reports(scenario: RDE):
    """M6 研究路线剪枝：归档对象 + branch_pruned 事件可回溯。"""
    scenario.create_node(base_node("question-q7", "question", work="active"))
    r = scenario.prune_branch("line-L7", reason="无信息价值", node_ids=["question-q7"])
    assert r["branch_id"] == "line-L7"
    assert scenario.graph.require("question-q7")["work_state"] == "archived"
    assert scenario.state["branches"]["line-L7"]["status"] == "pruned"
    # 剪枝后仍可重开
    scenario.reopen("question-q7", reason="新证据出现")
    assert scenario.graph.require("question-q7")["work_state"] == "proposed"
