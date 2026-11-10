"""图结构测试：超边、一证据多命题、多推导路线、严格关系语义、schema 校验。

对应验收标准 3 / 4，任务书 §3、§4、graph_semantics.md。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from core import RDE
from core.errors import ValidationError
from core.graph import validate_edge

from conftest import base_node, claim, evidence, TS

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- 超边

def test_hyperedge_multiple_premises_and_conclusions(rde: RDE):
    """多前提汇合 + 多结论共享前提的超边（任务书 §3：不限制为树）。"""
    rde.create_node(base_node("definition-x", "definition", scope="全局"))
    rde.create_node(base_node("assumption-y", "assumption"))
    rde.create_node(claim("claim-p", [], [], [], work="proposed"))
    rde.create_node(claim("claim-q", [], [], [], work="proposed"))
    rde.create_edge({
        "id": "edge-entails-001", "type": "entails", "category": "logical",
        "premises": ["definition-x", "assumption-y"],
        "conclusions": ["claim-p", "claim-q"],
        "created_at": TS, "source": {"origin": "human"}, "scope": "示例范围",
        "validity": "active",
    })
    edge = rde.graph.get_edge("edge-entails-001")
    assert len(edge["premises"]) == 2 and len(edge["conclusions"]) == 2
    assert rde.graph.downstream(["assumption-y"]) == ["claim-p", "claim-q"]


def test_edge_category_semantics_must_match_type():
    """关系语义严格分离：supports 不得标成 logical 类别（§3.2）。"""
    bad = {
        "id": "edge-bad-001", "type": "supports", "category": "logical",
        "premises": ["evidence-e1"], "conclusions": ["claim-p"],
        "created_at": TS, "source": {"origin": "human"}, "validity": "active",
    }
    with pytest.raises(ValidationError, match="类别不一致"):
        validate_edge(bad)


# ---------------------------------------------------------------- 一个证据 ↔ 多命题（验收标准 3）

def test_one_evidence_multiple_claims(rde: RDE):
    rde.create_node(claim("claim-a", [], [], [], work="proposed"))
    rde.create_node(claim("claim-b", [], [], [], work="proposed"))
    ev = evidence("evidence-shared", supports=["claim-a"], contradicts=["claim-b"])
    rde.append_evidence(ev)
    # 同一证据 ID 同时出现在两个命题的证据集合中
    assert "evidence-shared" in rde.graph.require("claim-a")["current_evidence"]
    assert "evidence-shared" in rde.graph.require("claim-b")["current_evidence"]
    assert rde.graph.claims_supported_by("evidence-shared") == ["claim-a"]
    assert rde.graph.claims_contradicted_by("evidence-shared") == ["claim-b"]
    # 两个命题各向各的证据状态推进
    assert rde.graph.require("claim-a")["evidence_state"] == "supported"
    assert rde.graph.require("claim-b")["evidence_state"] == "contradicted"


# ---------------------------------------------------------------- 一命题 ↔ 多路线（验收标准 4）

def test_multiple_derivation_routes(scenario: RDE):
    routes = scenario.graph.derivations_for("claim-c1")
    ids = [d["id"] for d in routes]
    assert ids == ["derivation-d1", "derivation-d2"]
    # 两条路线前提集合不同（结构上的独立性基础）
    p1 = set(scenario.graph.require("derivation-d1")["premises"])
    p2 = set(scenario.graph.require("derivation-d2")["premises"])
    assert p1 != p2


def test_evidence_edge_cannot_masquerade_as_entailment(rde: RDE):
    """证据支持绝不蕴含逻辑蕴含：两个方向都要能表达且互斥。"""
    rde.create_node(claim("claim-e", [], [], [], work="proposed"))
    rde.append_evidence(evidence("evidence-e9", supports=["claim-e"]))
    logical = [e for e in rde.graph.edges.values() if e["type"] == "entails"]
    assert logical == []          # 经验支持没有自动生成任何逻辑边


# ---------------------------------------------------------------- schema 校验

def _registry() -> Registry:
    registry = Registry()
    for p in sorted((REPO / "schemas").glob("*.schema.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        registry = registry.with_resource(
            uri=data["$id"], resource=Resource.from_contents(data, default_specification=DRAFT202012)
        )
    return registry


def test_claim_and_evidence_examples_match_schemas():
    """示例数据必须通过 schemas/ 校验（M1 标准化）。"""
    registry = _registry()

    def load(name: str) -> dict:
        return json.loads((REPO / "schemas" / name).read_text(encoding="utf-8"))

    claim_v = Draft202012Validator(load("claim.schema.json"), registry=registry)
    evidence_v = Draft202012Validator(load("evidence.schema.json"), registry=registry)
    edge_v = Draft202012Validator(load("edge.schema.json"), registry=registry)

    ucs = json.loads((REPO / "examples" / "ucs_example.json").read_text(encoding="utf-8"))
    trvc = json.loads((REPO / "examples" / "trvc_example.json").read_text(encoding="utf-8"))

    claims = [a["claim"] for a in ucs["state_demo"]["assignments"]]
    claims += trvc["knowledge_items"]
    for c in claims:
        claim_v.validate(c)

    evidence_v.validate(
        {"id": "evidence-ucs-ce1", "type": "evidence", "version": 1, "created_at": TS,
         "source": {"origin": "human"}, "scope": "x", "content": "占位",
         "evidence_kind": "counterexample", "validity": "valid"}
    )
    for e in ucs["constraint_patterns"]:
        edge_v.validate({k: v for k, v in e.items() if k not in ("kind_of_constraint", "pattern", "placeholder")})
    edge_v.validate(trvc["exception_learning_demo"]["shape"]["linking_edge"])


def test_examples_declare_their_epistemic_status():
    """示例必须自带状态声明：不得把占位数据伪装成实验结论（第 8 节边界）。"""
    w3 = json.loads((REPO / "examples" / "w3_example.json").read_text(encoding="utf-8"))
    assert w3["_meta"]["pilot_approved"] is False
    assert "NOT APPROVED" in w3["_meta"]["status"]
    # 预测/实际必须保持占位
    assert w3["prediction_vs_actual"]["predicted"] is None
    assert w3["prediction_vs_actual"]["actual"] is None
    ucs = json.loads((REPO / "examples" / "ucs_example.json").read_text(encoding="utf-8"))
    assert "不是 UCS 研究的真实实验结论" in " ".join(ucs["_meta"]["warnings"])
    trvc = json.loads((REPO / "examples" / "trvc_example.json").read_text(encoding="utf-8"))
    assert any("不得重新解释或篡改" in w for w in trvc["_meta"]["warnings"])
