"""共享测试场景。

场景 A（多路线）：definition-d1/d2、assumption-a1/a2、
claim-c1（两条路线 d1/d2）、claim-c2（单路线 d3）、claim-c3（证据对象）。
前提关系由节点字段（routes/premises/dependency_nodes）承载 —— 不预设必须有显式边。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core import RDE

TS = "2026-01-01T00:00:00Z"


def claim(cid: str, routes: list[str], deps: list[str], asums: list[str],
          work: str = "active", prop: str = "unknown", evid: str = "none") -> dict:
    return {
        "id": cid, "type": "claim", "version": 1, "created_at": TS,
        "source": {"origin": "human"}, "scope": "示例范围", "content": f"占位命题 {cid}",
        "definition_versions": [{"id": d, "version": 1} for d in deps],
        "assumptions": [{"id": a, "version": 1} for a in asums],
        "dependency_nodes": list(deps) + list(asums),
        "proof_obligations": [
            {"id": f"po-{cid}", "statement": "占位义务", "track": "mathematical", "status": "open"}
        ],
        "falsification_conditions": ["占位反证条件"],
        "current_evidence": [],
        "proposition_state": prop, "evidence_state": evid, "work_state": work,
        "next_research_action": {"action": "占位下一步", "decision_ref": None},
        "routes": routes,
    }


def base_node(nid: str, ntype: str, content: str = "", scope: str = "示例范围",
              work: str = "proposed") -> dict:
    return {
        "id": nid, "type": ntype, "version": 1, "created_at": TS,
        "source": {"origin": "human"}, "scope": scope, "content": content or nid,
        "work_state": work,
    }


def derivation(did: str, premises: list[str], concludes: list[str],
               status: str = "draft") -> dict:
    return {
        "id": did, "type": "derivation", "version": 1, "created_at": TS,
        "source": {"origin": "human"}, "scope": "示例范围", "content": f"推导 {did}",
        "premises": premises, "concludes": concludes, "track": "mathematical",
        "status": status, "work_state": "active",
    }


def evidence(eid: str, supports: list[str] | None = None, contradicts: list[str] | None = None,
             kind: str = "experimental", validity: str = "valid") -> dict:
    return {
        "id": eid, "type": "evidence", "version": 1, "created_at": TS,
        "source": {"origin": "human", "ref": "placeholder-source"}, "scope": "示例范围",
        "content": f"证据 {eid}", "evidence_kind": kind, "validity": validity,
        "supports": list(supports or []), "contradicts": list(contradicts or []),
        "work_state": "active",
    }


@pytest.fixture()
def rde() -> RDE:
    return RDE()


@pytest.fixture()
def scenario(rde: RDE) -> RDE:
    """多证明路线场景（验收标准 4/5 的标准夹具）。"""
    for did in ("definition-d1", "definition-d2"):
        rde.create_node(base_node(did, "definition", scope="全局"))
    for aid in ("assumption-a1", "assumption-a2"):
        rde.create_node(base_node(aid, "assumption"))
    rde.create_node(claim("claim-c1", ["derivation-d1", "derivation-d2"],
                          ["definition-d1"], ["assumption-a1"]))
    rde.create_node(claim("claim-c2", ["derivation-d3"],
                          ["definition-d1"], ["assumption-a1"]))
    rde.start_derivation(derivation("derivation-d1", ["assumption-a1", "definition-d1"], ["claim-c1"]))
    rde.start_derivation(derivation("derivation-d2", ["assumption-a2", "definition-d2"], ["claim-c1"]))
    rde.start_derivation(derivation("derivation-d3", ["assumption-a1", "definition-d1"], ["claim-c2"]))
    return rde
