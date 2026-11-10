"""对抗审计 G — Schema 与实现一致性（schemas/ ↔ core/）。

发现编号见 reports/adversarial_audit.md（F-Gxx）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from core import RDE

from conftest import base_node, claim, evidence, derivation

REPO = Path(__file__).resolve().parents[2]


def _registry() -> Registry:
    reg = Registry()
    for p in sorted((REPO / "schemas").glob("*.schema.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        reg = reg.with_resource(uri=data["$id"],
                                resource=Resource.from_contents(data,
                                                                default_specification=DRAFT202012))
    return reg


def _validator(name: str) -> Draft202012Validator:
    data = json.loads((REPO / "schemas" / name).read_text(encoding="utf-8"))
    return Draft202012Validator(data, registry=_registry())


# ---------------------------------------------------------------- G1 多节点影响报告

def test_g01_multi_node_impact_event_validates_against_schema(rde: RDE):
    """F-G1（修复前失败）：Δ 含多节点时 change.node 是数组 —— schema 必须允许它
    （dependency_propagation 的输入是 {node: kind} 多元组，算法文档明确支持 Δ 集合）。"""
    for d in ("definition-m1", "definition-m2"):
        rde.create_node(base_node(d, "definition", scope="全局", work="active"))
    rde.impact({"definition-m1": "modified", "definition-m2": "refuted"})
    event = rde.log.by_type("impact_report_generated")[-1]
    errors = list(_validator("event.schema.json").iter_errors(event))
    assert errors == [], f"多节点影响报告事件必须通过 schema: {[e.message for e in errors]}"


def test_g01b_single_node_impact_event_validates(rde: RDE):
    rde.create_node(base_node("definition-s1", "definition", scope="全局", work="active"))
    rde.revise_node("definition-s1", {"content": "v2"}, reason="schema 测试")
    event = rde.log.by_type("impact_report_generated")[-1]
    assert list(_validator("event.schema.json").iter_errors(event)) == []


# ---------------------------------------------------------------- G2 样本日志

def test_g02_all_sample_log_events_validate():
    from core import EventLog
    log = EventLog.load_jsonl(REPO / "examples" / "events_sample.jsonl")
    v = _validator("event.schema.json")
    bad = []
    for ev in log.events:
        errs = list(v.iter_errors(ev))
        if errs:
            bad.append((ev["event_id"], ev["type"], [e.message for e in errs]))
    assert bad == [], f"样本日志中存在不合 schema 的事件: {bad}"


def test_g02b_rich_scenario_events_validate(rde: RDE):
    """构造覆盖多类事件的场景，逐事件过 schema（node/edge/state/evidence/decision/branch/fork）。"""
    rde.create_node(base_node("definition-r1", "definition", scope="全局", work="active"))
    rde.create_node(claim("claim-r1", ["derivation-r1"], ["definition-r1"],
                          ["assumption-r1"], work="proposed"))
    rde.start_derivation(derivation("derivation-r1", ["assumption-r1"], ["claim-r1"]))
    rde.fork_definition("definition-r1", "definition-r1-alt", changes={"content": "分叉"})
    rde.append_evidence(evidence("evidence-r1", supports=["claim-r1"]))
    rde.invalidate_evidence("evidence-r1", reason="测试")
    rde.record_decision({"goal": "g", "options": ["a", "b"], "rationale": "r",
                         "budget": {}, "expected_value": {}},
                        node_id="decision-r1", actor="human")
    rde.branch("branch-r1")
    rde.prune_branch("branch-r1", reason="无信息", node_ids=[])
    rde.revise_node("definition-r1", {"content": "v2"}, reason="schema")
    v = _validator("event.schema.json")
    bad = [(ev["event_id"], ev["type"], [e.message for e in list(v.iter_errors(ev))])
           for ev in rde.log.events if list(v.iter_errors(ev))]
    assert bad == [], bad


# ---------------------------------------------------------------- G3 sufficiency 字段

def test_g03_evidence_schema_declares_sufficiency():
    """F-D3：core 读取 sufficiency 决定 insufficient，schema 必须声明它（枚举受限）。"""
    schema = json.loads((REPO / "schemas" / "evidence.schema.json").read_text(encoding="utf-8"))
    assert "sufficiency" in schema["properties"]
    prop = schema["properties"]["sufficiency"]
    assert prop["enum"] == ["sufficient", "insufficient"]


# ---------------------------------------------------------------- G4/G5 边与 ID

def test_g04_edge_schema_rejects_category_mix():
    v = _validator("edge.schema.json")
    bad = {"id": "edge-x", "type": "entails", "category": "evidential",
           "premises": ["a"], "conclusions": ["b"],
           "created_at": "2026-01-01T00:00:00Z", "source": {"origin": "human"},
           "validity": "active"}
    assert list(v.iter_errors(bad)), "schema 层也要拦截类别混用（与代码双闸门）"
    good = dict(bad, category="logical")
    assert list(v.iter_errors(good)) == []


def test_g05_node_id_pattern_requires_full_type_prefix():
    """ID 规则（graph_semantics §1）：短前缀（def-）不得通过 schema。"""
    v = _validator("node.schema.json")
    node = {"id": "def-ucs-c1", "type": "definition", "version": 1,
            "created_at": "2026-01-01T00:00:00Z", "source": {"origin": "human"},
            "scope": "x", "content": "c"}
    assert list(v.iter_errors(node)), "def- 前缀必须被拒（应为 definition-）"
    node["id"] = "definition-ucs-c1"
    assert list(v.iter_errors(node)) == []
