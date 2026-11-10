"""对抗审计 E — 状态机与权限（docs/architecture.md §5、原则 4/9/10、state_semantics L1/L3）。

设计锚点：
- 原则 10：Agent 不得用自我生成的评价替代外部验证；agent 自评不能单独授予语义状态
- 原则 9：北极星修改只能 human，且第一阶段禁止
- L1：true/false 必须绑定假设与适用范围（含创建入口）
- L3：Claim → completed 必须先满足证明义务（数学轨/经验轨各自验收）

本文件中的多个测试在 Phase 1.1 审计前会失败（见 reports/adversarial_audit.md 的
F-E01/F-E02/F-E03/F-E04 修复记录）。修复是把实现拉回文档承诺，不是放松测试。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import RDE, IllegalTransition, ReplayError, replay
from core.errors import ValidationError

from conftest import base_node, claim

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


# ---------------------------------------------------------------- E1 agent 语义升级

def test_e01_agent_cannot_execute_truth_upgrade(rde: RDE):
    """原则 10/architecture §5：agent 只能*提议*语义升级，执行必须 human。"""
    rde.create_node(claim("claim-e1", [], [], [], work="formalized"))
    justification = {"route": "mathematical", "assumptions": [{"id": "assumption-x", "version": 1}]}
    # agent 直接执行 → 必须拒绝
    with pytest.raises(IllegalTransition, match="human|agent"):
        rde.set_proposition_state("claim-e1", "true_in_scope", justification=justification,
                                  actor="agent:audit")
    assert rde.graph.require("claim-e1")["proposition_state"] == "unknown"
    # agent 提议（proposed_only）→ 允许写入日志
    ev = rde.set_proposition_state("claim-e1", "true_in_scope", justification=justification,
                                   actor="agent:audit", proposed_only=True)
    assert ev["payload"].get("proposed_only") is True
    assert rde.graph.require("claim-e1")["proposition_state"] == "unknown", "提议不改变状态"
    # human 执行 → 允许
    rde.set_proposition_state("claim-e1", "true_in_scope", justification=justification,
                              actor="human")
    assert rde.graph.require("claim-e1")["proposition_state"] == "true_in_scope"


# ---------------------------------------------------------------- E2 创建入口绕过

def test_e02_truth_state_creation_requires_binding(rde: RDE):
    """L1 必须在创建入口同样生效：绕过状态机直接携带 true_in_scope 必须被拒。"""
    # 无假设绑定 → 拒绝
    with pytest.raises(ValidationError, match="绑定|假设"):
        rde.create_node(claim("claim-cheat", [], [], [], work="proposed",
                              prop="true_in_scope"))
    # 有假设绑定（claim fixture 的 assumptions 非空、scope 非空）→ 允许
    rde.create_node(claim("claim-ok", [], [], ["assumption-b"], work="proposed",
                          prop="true_in_scope"))
    assert rde.graph.require("claim-ok")["proposition_state"] == "true_in_scope"


def test_e02b_truth_state_requires_nonempty_scope(rde: RDE):
    node = claim("claim-noscope", [], [], ["assumption-b"], work="proposed",
                 prop="true_in_scope")
    node["scope"] = ""
    with pytest.raises(ValidationError, match="scope|范围"):
        rde.create_node(node)


# ---------------------------------------------------------------- E3 北极星

def test_e03_north_star_fully_gated(rde: RDE):
    """原则 9：引擎无北极星修改入口；即使绕过引擎手工写日志，重放与 schema 双双拒绝。"""
    assert not hasattr(rde, "modify_north_star")
    # 手工追加事件（human 也不行 —— 第一阶段禁令）
    rde.log.append("north_star_modified", actor="human", target=["project-rde"],
                   payload={"what": "demo"})
    with pytest.raises(ReplayError, match="第一阶段禁止"):
        replay(rde.log.events)
    # schema 层：actor 必须是 human（agent 连 schema 都过不了）
    schema = json.loads((SCHEMAS / "event.schema.json").read_text(encoding="utf-8"))
    from jsonschema import Draft202012Validator
    base = {"event_id": "evt-00000001", "seq": 99, "type": "north_star_modified",
            "timestamp": "2026-01-01T00:00:00Z", "target": ["project-rde"],
            "payload": {}, "prev_hash": "GENESIS", "hash": "0" * 64}
    assert not list(Draft202012Validator(schema).iter_errors({**base, "actor": "human"}))
    assert list(Draft202012Validator(schema).iter_errors({**base, "actor": "agent:x"}))


# ---------------------------------------------------------------- E4 未授权历史

def test_e04_unauthorized_illegal_history_rejected_on_replay(rde: RDE):
    """伪造『人类签署』的非法历史（blocked→completed）在重放层必须失败。"""
    rde.create_node(claim("claim-e4", [], [], [], work="proposed"))
    rde.set_work_state("claim-e4", "formalized")
    rde.set_work_state("claim-e4", "blocked", reason="等待")
    from core.events import compute_event_hash
    evs = rde.log.events
    bad = {"seq": len(evs), "type": "work_state_changed", "timestamp": "2026-01-01T00:00:00Z",
           "actor": "human", "target": ["claim-e4"],
           "payload": {"from": "blocked", "to": "completed"}, "prev_hash": rde.log.chain_head()}
    h = compute_event_hash(bad)
    bad.update(event_id=f"evt-{h[:8]}", hash=h)
    with pytest.raises(IllegalTransition, match="非法工作状态转换"):
        replay([*evs, bad])


# ---------------------------------------------------------------- E5 L3 证明义务

def test_e05_completed_requires_discharged_obligations(rde: RDE):
    """L3：Claim 在证明义务 open 时不得 completed；义务完成后方可。"""
    rde.create_node(claim("claim-e5", [], [], [], work="active"))   # obligations: open
    with pytest.raises(IllegalTransition, match="L3|义务"):
        rde.set_work_state("claim-e5", "completed")
    assert rde.graph.require("claim-e5")["work_state"] == "active"
    # 通过内容修订回填义务完成（义务状态变化是版本化内容变更）
    node = rde.graph.require("claim-e5")
    obligations = [dict(o, status="discharged", discharged_by="derivation-x")
                   for o in node["proof_obligations"]]
    rde.revise_node("claim-e5", {"proof_obligations": obligations}, reason="义务完成")
    rde.set_work_state("claim-e5", "completed")
    assert rde.graph.require("claim-e5")["work_state"] == "completed"


def test_e05b_completed_creation_bypass_blocked(rde: RDE):
    """创建入口同样执行 L3：直接以 completed + open 义务创建必须被拒。"""
    with pytest.raises(ValidationError, match="L3|义务"):
        rde.create_node(claim("claim-e5b", [], [], [], work="completed"))
    # 义务已完成的 claim 可以直接以 completed 创建
    node = claim("claim-e5c", [], [], [], work="completed")
    node["proof_obligations"] = [dict(o, status="discharged")
                                 for o in node["proof_obligations"]]
    rde.create_node(node)
    assert rde.graph.require("claim-e5c")["work_state"] == "completed"


# ---------------------------------------------------------------- E6 决策自评

def test_e06_agent_cannot_self_mark_decision_effective(rde: RDE):
    """原则 10：决策有效性回填需人类签署或外部验证引用。"""
    nid = rde.record_decision(
        {"goal": "g", "options": ["o"], "rationale": "r", "budget": {},
         "expected_value": {}},
        node_id="decision-e6", actor="agent:audit")
    # agent 无外部验证 → 拒绝
    with pytest.raises(IllegalTransition, match="外部验证|human|人类"):
        rde.backfill_decision(nid, actual_outcome="看起来不错",
                              decision_effective=True, actor="agent:audit")
    # agent 带外部验证引用 → 允许（外部证据背书）
    rde.backfill_decision(nid, actual_outcome="有外部审计记录",
                          decision_effective=True, actor="agent:audit",
                          external_validation_ref="external-audit-001")
    # human → 允许
    nid2 = rde.record_decision(
        {"goal": "g2", "options": ["o"], "rationale": "r", "budget": {},
         "expected_value": {}}, node_id="decision-e6b", actor="human")
    rde.backfill_decision(nid2, actual_outcome="ok", decision_effective=True, actor="human")


# ---------------------------------------------------------------- E7 间接绕过

def test_e07_indirect_state_smuggling_rejected(rde: RDE):
    """经 revise_node 夹带状态字段（间接绕过状态机）必须被拒。"""
    rde.create_node(claim("claim-e7", [], [], [], work="proposed"))
    with pytest.raises(ValidationError, match="状态字段"):
        rde.revise_node("claim-e7", {"proposition_state": "true_in_scope"}, reason="绕过")
    with pytest.raises(ValidationError, match="状态字段"):
        rde.revise_node("claim-e7", {"work_state": "completed"}, reason="绕过")
    with pytest.raises(ValidationError, match="状态字段"):
        rde.revise_node("claim-e7", {"evidence_state": "supported"}, reason="绕过")


def test_e08_agent_actor_allowed_for_operational_work_states(rde: RDE):
    """边界确认：工作状态（流程性）允许 agent 推进；受限的是语义状态与授权事件。
    （避免把权限修成『agent 什么都不能做』—— 这是设计边界的一部分。）"""
    rde.create_node(claim("claim-e8", [], [], [], work="proposed"))
    rde.set_work_state("claim-e8", "formalized", actor="agent:worker")
    assert rde.graph.require("claim-e8")["work_state"] == "formalized"
    # 但 agent 不得签发人类授权
    with pytest.raises(IllegalTransition, match="human"):
        rde.approve("evt-00000000", note="x", actor="agent:worker")


# ---------------------------------------------------------------- E9/E10 文档缺口固化

def test_e09_l1_derivation_existence_subcondition_not_enforced(rde: RDE):
    """F-E09（开放，见 adversarial_audit 与 consistency 报告）：
    state_semantics L1 的完整定义是『存在一条 completed 的 Derivation 路线 +
    assumptions/scope 绑定』。当前实现只检查了*绑定*子条件；
    『completed 推导路线存在』子条件未检查。本测试固化该事实（不作为正确性证据），
    且注意到与 refute 路径（原则 5 反例离场）的张力 —— 需研究者裁决 L1 的精确边界。
    """
    rde.create_node(claim("claim-e9", [], [], ["assumption-b"], work="active"))
    # 图中不存在任何 derives 它的 completed 推导，仍可升为 true_in_scope
    rde.set_proposition_state(
        "claim-e9", "true_in_scope",
        justification={"route": "mathematical",
                       "assumptions": [{"id": "assumption-b", "version": 1}]})
    assert rde.graph.require("claim-e9")["proposition_state"] == "true_in_scope"


def test_e10_l2_definition_version_determination_not_enforced(rde: RDE):
    """F-E10（开放）：state_semantics L2『proposed → formalized 的前置条件：
    所有引用的 Definition 版本已确定（版本事件存在）』当前未实现 ——
    引用不存在/无版本事件的定义也可 formalized。固化事实，待研究者裁决。
    """
    node = claim("claim-e10", [], ["definition-ghost"], [], work="proposed")
    # 引用的 definition-ghost 在图中根本不存在，其版本事件更不存在
    node["definition_versions"] = [{"id": "definition-ghost", "version": 1}]
    rde.create_node(node)
    rde.set_work_state("claim-e10", "formalized")   # L2 未实现 → 不应在此处被拒
    assert rde.graph.require("claim-e10")["work_state"] == "formalized"
