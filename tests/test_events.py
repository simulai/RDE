"""事件溯源测试：重放一致性、哈希链、未知事件、决策回溯、JSONL 往返。

对应验收标准 1 / 8，docs/event_sourcing.md。
"""

from __future__ import annotations

import copy

import pytest

from core import RDE, EventLog, ChainBroken, ReplayError, replay, state_digest
from core.errors import ValidationError

from conftest import base_node, claim, TS


def _build(log: EventLog | None = None) -> RDE:
    rde = RDE(log)
    rde.create_node(base_node("definition-d1", "definition", scope="全局"))
    rde.create_node(base_node("assumption-a1", "assumption"))
    rde.create_node(claim("claim-c1", ["derivation-d1"], ["definition-d1"], ["assumption-a1"]))
    return rde


def test_replay_consistency():
    """验收标准 1：同一份事件日志能够重建同一知识状态。"""
    a = _build()
    a.refute("assumption-a1")
    a.append_evidence({
        "id": "evidence-e1", "type": "evidence", "version": 1, "created_at": TS,
        "source": {"origin": "human"}, "scope": "示例范围", "content": "证据",
        "evidence_kind": "experimental", "validity": "valid",
        "supports": ["claim-c1"], "contradicts": [], "work_state": "active",
    })
    digest_a = a.digest()

    # 同一日志，独立重放两次
    d1 = state_digest(replay(a.log.events))
    d2 = state_digest(replay(list(reversed(a.log.events))))  # 乱序输入也必须按 seq 归一
    assert d1 == d2 == digest_a

    # 通过 EventLog 重载（含链校验）再重放
    b = RDE(EventLog(a.log.events))
    assert b.digest() == digest_a
    assert b.verify() is True


def test_hash_chain_tamper_detected():
    """原则 8 / F-ES-02：历史被静默修改必须断链。"""
    rde = _build()
    tampered = copy.deepcopy(rde.log.events)
    tampered[1]["payload"]["node"]["content"] = "被偷偷改掉的内容"
    with pytest.raises(ChainBroken):
        EventLog(tampered)          # 构造时即校验
    with pytest.raises(ChainBroken):
        EventLog(tampered, verify=False).verify_chain()


def test_unknown_event_type_fails_replay():
    """重放遇到未知事件类型必须失败，不得静默跳过。"""
    rde = _build()
    events = rde.log.events + [{
        "event_id": "evt-deadbeef", "seq": len(rde.log), "type": "mystery_event",
        "timestamp": TS, "actor": "system", "target": ["claim-c1"],
        "payload": {}, "prev_hash": rde.log.chain_head(), "hash": "0" * 64,
    }]
    with pytest.raises(ReplayError, match="未知事件类型"):
        replay(events)


def test_decision_traceability():
    """验收标准 8：所有研究决策可以回溯（M7 七字段 + 事件 actor）。"""
    rde = _build()
    decision = {
        "goal": "占位：验证路线价值",
        "options": ["路线A", "路线B"],
        "rationale": "占位：选择理由",
        "budget": {"compute_units": 10},
        "expected_value": {"information_gain": None, "falsification_value": None,
                           "contribution_note": "分维度记录，不合并评分"},
        "actual_outcome": None, "decision_effective": None,
        "external_validation_ref": None,
    }
    nid = rde.record_decision(decision, node_id="decision-test-d1", actor="human")
    # 写入事件可回溯：类型、actor、目标
    events = rde.log.by_type("decision_recorded")
    assert len(events) == 1
    ev = events[0]
    assert ev["actor"] == "human" and ev["target"] == [nid]
    assert rde.state["decisions"][nid]["rationale"] == "占位：选择理由"
    # 实际结果回填（M7）
    rde.backfill_decision(nid, actual_outcome="路线A 无信息价值",
                          decision_effective=False,
                          external_validation_ref="audit-001")
    stored = rde.state["decisions"][nid]
    assert stored["decision_effective"] is False
    assert stored["external_validation_ref"] == "audit-001"
    # 回填产生新版本，旧决策记录仍在事件日志
    assert rde.graph.require(nid)["version"] == 2


def test_jsonl_roundtrip(tmp_path):
    rde = _build()
    rde.refute("assumption-a1")
    path = tmp_path / "events.jsonl"
    rde.save(path)
    restored = RDE.restore(path)
    assert restored.digest() == rde.digest()
    assert len(restored.log) == len(rde.log)
    assert restored.log.verify_chain() is True


def test_impact_report_is_an_event(scenario: RDE):
    """基础节点变化必须产生依赖影响报告事件（原则 7、验收标准 7）。"""
    before = len(scenario.log.by_type("impact_report_generated"))
    scenario.revise_node("definition-d1", {"content": "v2"}, reason="test")
    reports = scenario.log.by_type("impact_report_generated")
    assert len(reports) == before + 1
    rep = reports[-1]["payload"]
    assert rep["change"]["node"] == "definition-d1"
    assert "claim-c1" in rep["directly_affected"]
    # 重放后报告仍在
    rebuilt = replay(scenario.log.events)
    assert len(rebuilt["reports"]) == len(reports)


def test_proposed_state_change_needs_human_approval(scenario: RDE):
    """H-DEP-002：推翻只产生*提议*，执行需人类授权；命题状态不被自动改变。"""
    from core import IllegalTransition
    # 先把 c2 的唯一路线走通：语义状态 true_in_scope（绑定假设与范围）
    scenario.set_proposition_state(
        "claim-c2", "true_in_scope",
        justification={"route": "mathematical",
                       "assumptions": [{"id": "assumption-a1", "version": 1}]})
    assert scenario.graph.require("claim-c2")["proposition_state"] == "true_in_scope"

    scenario.refute("assumption-a1")   # c2 唯一路线失效 → 报告 + 提议
    proposals = scenario.state["proposals"]
    assert any(p["node_id"] == "claim-c2" and p.get("proposed_only")
               and p["to"] == "unknown" for p in proposals)
    # 关键：提议 ≠ 执行（验收标准 5 + 原则 9/10）——状态仍未被自动改变
    assert scenario.graph.require("claim-c2")["proposition_state"] == "true_in_scope"
    # 提议事件本身可回溯
    proposal_events = [e for e in scenario.log.by_type("proposition_state_changed")
                       if e["payload"].get("proposed_only")]
    assert proposal_events
    # 非 human actor 不得签发授权
    with pytest.raises(IllegalTransition, match="human"):
        scenario.approve(proposal_events[-1]["event_id"], actor="agent:x")
    # 人类批准 + 显式转换事件后才执行
    scenario.approve(proposal_events[-1]["event_id"], note="批准离场")
    scenario.set_proposition_state("claim-c2", "unknown",
                                   justification={"route": "scope_change"})
    assert scenario.graph.require("claim-c2")["proposition_state"] == "unknown"
