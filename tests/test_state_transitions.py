"""状态转换测试：合法转换、非法升级、双轨分离、冲突证据不被覆盖、reopen 约束。

对应验收标准 6 / 9，docs/state_semantics.md（Task 3）。
"""

from __future__ import annotations

import pytest

from core import RDE, IllegalTransition
from core import state_machine as sm

from conftest import base_node, claim, evidence


# ---------------------------------------------------------------- 转换表本身

def test_legal_transitions_accepted():
    sm.check_proposition_transition("unknown", "true_in_scope",
                                    justification={"route": "mathematical",
                                                   "assumptions": [{"id": "a1", "version": 1}]},
                                    scope="范围")
    sm.check_proposition_transition("true_in_scope", "unknown",
                                    justification={"route": "scope_change"})
    sm.check_evidence_transition("none", "supported", driven_by=["evidence_appended"])
    sm.check_evidence_transition("supported", "mixed", driven_by=["evidence_appended"])
    sm.check_evidence_transition("mixed", "invalidated", driven_by=["evidence_invalidated"])
    sm.check_work_transition("proposed", "formalized")
    sm.check_work_transition("archived", "proposed", reopen=True)


def test_illegal_transitions_rejected():
    with pytest.raises(IllegalTransition, match="no-op"):
        sm.check_work_transition("active", "active")
    with pytest.raises(IllegalTransition, match="非法命题状态转换"):
        sm.check_proposition_transition("not_applicable", "underdetermined",
                                        justification={"route": "mathematical",
                                                       "assumptions": [{"id": "a", "version": 1}]},
                                        scope="x")
    # 跳过形式化直接完成（任务书 Task 7：非法状态升级）
    with pytest.raises(IllegalTransition, match="非法工作状态转换"):
        sm.check_work_transition("proposed", "completed")
    # 未解除阻塞不得完成
    with pytest.raises(IllegalTransition, match="非法工作状态转换"):
        sm.check_work_transition("blocked", "completed")
    # 终态重开必须显式 reopen
    with pytest.raises(IllegalTransition, match="reopen"):
        sm.check_work_transition("archived", "proposed")


def test_cross_dimension_write_rejected():
    """三维度不得互相写入：工作状态 'proposed' 不是命题状态。"""
    with pytest.raises(IllegalTransition, match="跨维度"):
        sm.check_proposition_transition("proposed", "true_in_scope",
                                        justification={"route": "mathematical",
                                                       "assumptions": [{"id": "a", "version": 1}]},
                                        scope="x")


def test_truth_requires_assumption_and_scope_binding():
    """原则 4：true_in_scope 必须绑定假设与适用范围。"""
    with pytest.raises(IllegalTransition, match="假设"):
        sm.check_proposition_transition("unknown", "true_in_scope",
                                        justification={"route": "mathematical", "assumptions": []},
                                        scope="x")
    with pytest.raises(IllegalTransition, match="范围"):
        sm.check_proposition_transition("unknown", "true_in_scope",
                                        justification={"route": "mathematical",
                                                       "assumptions": [{"id": "a", "version": 1}]},
                                        scope="")
    with pytest.raises(IllegalTransition, match="缺少 justification"):
        sm.check_proposition_transition("unknown", "true_in_scope")


# ---------------------------------------------------------------- 经验轨不授予语义状态（验收标准 9）

def test_cross_track_upgrade_rejected_in_engine(rde: RDE):
    rde.create_node(claim("claim-x", [], [], [], work="proposed"))
    rde.append_evidence(evidence("evidence-x", supports=["claim-x"]))
    assert rde.graph.require("claim-x")["evidence_state"] == "supported"
    # 证据再好，也不能作为语义升级的理由（F-R1.2）
    with pytest.raises(IllegalTransition, match="经验轨|empirical"):
        rde.set_proposition_state("claim-x", "true_in_scope",
                                  justification={"route": "empirical",
                                                 "evidence": ["evidence-x"]})
    assert rde.graph.require("claim-x")["proposition_state"] == "unknown"


def test_evidence_state_cannot_be_driven_by_derivation_event(rde: RDE):
    rde.create_node(claim("claim-y", [], [], [], work="proposed"))
    with pytest.raises(IllegalTransition, match="证据类事件"):
        rde.set_evidence_state("claim-y", "supported", driven_by=["derivation_completed"])


def test_work_state_cannot_jump_to_completed_via_engine(rde: RDE):
    rde.create_node(claim("claim-z", [], [], [], work="proposed"))
    with pytest.raises(IllegalTransition, match="非法工作状态转换"):
        rde.set_work_state("claim-z", "completed")
    # 合法推进到 completed：formalized → active → completed
    rde.set_work_state("claim-z", "formalized")
    rde.set_work_state("claim-z", "active")
    # L3（state_semantics §4）：证明义务未完成时，completed 仍必须被拒。
    # [Phase 1.1 披露] 本用例在 Phase 1.1 审计前的版本直接允许了这次 completed，
    # 与文档 L3 冲突（F-E03）；此处按*文档设计*修正期望，不是放松断言。
    with pytest.raises(IllegalTransition, match="L3"):
        rde.set_work_state("claim-z", "completed")
    # 证明义务回填完成后（经内容修订，版本化留痕）方可 completed
    node = rde.graph.require("claim-z")
    obligations = [dict(o, status="discharged", discharged_by="derivation-z")
                   for o in node["proof_obligations"]]
    rde.revise_node("claim-z", {"proof_obligations": obligations}, reason="证明义务完成")
    rde.set_work_state("claim-z", "completed")
    assert rde.graph.require("claim-z")["work_state"] == "completed"


# ---------------------------------------------------------------- 冲突证据（验收标准 6）

def test_conflicting_evidence_not_overwritten(rde: RDE):
    rde.create_node(claim("claim-w", [], [], [], work="proposed"))
    rde.append_evidence(evidence("evidence-s1", supports=["claim-w"]))
    assert rde.graph.require("claim-w")["evidence_state"] == "supported"
    # 冲突到达 → mixed，双方保留
    rde.append_evidence(evidence("evidence-c1", contradicts=["claim-w"]))
    assert rde.graph.require("claim-w")["evidence_state"] == "mixed"
    # 再来一条支持 → 仍是 mixed（不因数量优势静默覆盖）
    rde.append_evidence(evidence("evidence-s2", supports=["claim-w"]))
    assert rde.graph.require("claim-w")["evidence_state"] == "mixed"
    # 冲突双方都还在证据集合里
    current = rde.graph.require("claim-w")["current_evidence"]
    assert "evidence-s1" in current and "evidence-c1" in current
    # 只有显式失效后才离开 mixed：失效反驳方 → supported（经 invalidated 中转）
    rde.invalidate_evidence("evidence-c1", reason="来源撤回")
    assert rde.graph.require("claim-w")["evidence_state"] == "supported"
    # 失效的证据仍可回溯（不删除）
    assert rde.graph.require("evidence-c1")["validity"] == "invalidated"
    assert rde.graph.require("evidence-c1")["invalidation"]["reason"] == "来源撤回"


def test_direct_supported_to_contradicted_blocked(rde: RDE):
    """supported → contradicted 不得绕过 mixed/失效路径单步到达。"""
    rde.create_node(claim("claim-v", [], [], [], work="proposed"))
    rde.append_evidence(evidence("evidence-s9", supports=["claim-v"]))
    with pytest.raises(IllegalTransition):
        # 模拟绕过流程的直接写入（driven_by 声称来自追加事件，但当前支撑证据仍有效）
        rde.set_evidence_state("claim-v", "contradicted", driven_by=["evidence_appended"])


def test_reopen_flow(rde: RDE):
    """M6 Reopen：归档问题可显式重开，但不能静默回 active。"""
    rde.create_node(base_node("question-q1", "question", work="proposed"))
    rde.set_work_state("question-q1", "formalized")
    rde.set_work_state("question-q1", "active")
    rde.set_work_state("question-q1", "archived", reason="暂关闭")
    with pytest.raises(IllegalTransition, match="非法工作状态转换"):
        rde.set_work_state("question-q1", "active")     # archived → active 无此路径
    with pytest.raises(IllegalTransition, match="reopen"):
        rde.set_work_state("question-q1", "proposed")   # 缺 reopen 标记
    rde.reopen("question-q1", reason="旧问题重新开放")
    assert rde.graph.require("question-q1")["work_state"] == "proposed"
    assert any(r["node_id"] == "question-q1" for r in rde.state["reopened"])
