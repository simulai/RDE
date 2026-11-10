"""对抗审计 D — 证据冲突与撤回/失效（docs/state_semantics.md §2、验收标准 6）。

设计锚点：
- 冲突 → mixed，双方保留；离开 mixed 必须经显式失效（不被覆盖）
- 证据永不删除：只有 invalidated / withdrawn，且带原因与 actor
- sufficiency → insufficient 的通路（F-D3：该机制原未入 schema，本轮补录）
"""

from __future__ import annotations

import pytest

from core import RDE, IllegalTransition

from conftest import claim, evidence


def _add(rde: RDE, eid, supports=(), contradicts=(), **kw):
    e = evidence(eid, supports=list(supports), contradicts=list(contradicts),
                 kind=kw.pop("kind", "experimental"), validity=kw.pop("validity", "valid"))
    e.update(kw)
    return e


def _state(rde: RDE, cid: str) -> str:
    return rde.graph.require(cid)["evidence_state"]


# ---------------------------------------------------------------- D1 共存与撤回

def test_d01_support_and_contradict_coexist_mixed(rde: RDE):
    rde.create_node(claim("claim-d1", [], [], [], work="proposed"))
    rde.append_evidence(_add(rde, "evidence-s1", supports=["claim-d1"]))
    rde.append_evidence(_add(rde, "evidence-c1", contradicts=["claim-d1"]))
    assert _state(rde, "claim-d1") == "mixed"
    cur = rde.graph.require("claim-d1")["current_evidence"]
    assert {"evidence-s1", "evidence-c1"} <= set(cur)


def test_d02_withdraw_one_side_via_withdraw_api(rde: RDE):
    """撤回（withdrawn）反驳方 → 经 invalidated 中转回到 supported；撤回的证据保留可查。"""
    rde.create_node(claim("claim-d2", [], [], [], work="proposed"))
    rde.append_evidence(_add(rde, "evidence-s2", supports=["claim-d2"]))
    rde.append_evidence(_add(rde, "evidence-c2", contradicts=["claim-d2"]))
    assert _state(rde, "claim-d2") == "mixed"

    assert hasattr(rde, "withdraw_evidence"), "withdraw_evidence API 应存在（event_sourcing §3）"
    rde.withdraw_evidence("evidence-c2", reason="来源撤稿")

    assert _state(rde, "claim-d2") == "supported"
    ev_node = rde.graph.require("evidence-c2")
    assert ev_node["validity"] == "withdrawn"
    assert ev_node["invalidation"]["reason"] == "来源撤稿"
    # 证据与历史事件都保留（原则 8）
    assert "evidence-c2" in rde.graph.require("claim-d2")["current_evidence"]
    assert rde.log.by_type("evidence_withdrawn")


def test_d03_invalidate_supporting_side_gives_contradicted(rde: RDE):
    """失效支持方（mixed）→ contradicted，转换序列必须经 invalidated。"""
    rde.create_node(claim("claim-d3", [], [], [], work="proposed"))
    rde.append_evidence(_add(rde, "evidence-s3", supports=["claim-d3"]))
    rde.append_evidence(_add(rde, "evidence-c3", contradicts=["claim-d3"]))
    assert _state(rde, "claim-d3") == "mixed"
    rde.invalidate_evidence("evidence-s3", reason="数据错误")
    assert _state(rde, "claim-d3") == "contradicted"
    seq = [(e["payload"]["from"], e["payload"]["to"])
           for e in rde.log.by_type("evidence_state_changed")]
    assert ("mixed", "invalidated") in seq and ("invalidated", "contradicted") in seq, \
        "必须经 invalidated 中转，不得单步覆盖"


def test_d04_new_evidence_keeps_mixed(rde: RDE):
    """冲突后新增第三条（任意方向）→ 仍为 mixed，不因数量/方向优势坍缩。"""
    rde.create_node(claim("claim-d4", [], [], [], work="proposed"))
    rde.append_evidence(_add(rde, "evidence-a", supports=["claim-d4"]))
    rde.append_evidence(_add(rde, "evidence-b", contradicts=["claim-d4"]))
    rde.append_evidence(_add(rde, "evidence-c", supports=["claim-d4"]))
    rde.append_evidence(_add(rde, "evidence-d", contradicts=["claim-d4"]))
    assert _state(rde, "claim-d4") == "mixed"


def test_d05_all_evidence_invalidated_state_invalidated(rde: RDE):
    rde.create_node(claim("claim-d5", [], [], [], work="proposed"))
    rde.append_evidence(_add(rde, "evidence-only", supports=["claim-d5"]))
    assert _state(rde, "claim-d5") == "supported"
    rde.invalidate_evidence("evidence-only", reason="全部失效")
    assert _state(rde, "claim-d5") == "invalidated"


# ---------------------------------------------------------------- D6 insufficient

def test_d06_insufficient_evidence_state(rde: RDE):
    """仅存在被标记 insufficient 的证据 → evidence_state = insufficient（且该字段入 schema）。"""
    rde.create_node(claim("claim-d6", [], [], [], work="proposed"))
    rde.append_evidence(_add(rde, "evidence-weak", supports=["claim-d6"],
                             sufficiency="insufficient"))
    assert _state(rde, "claim-d6") == "insufficient"
    # schema 必须声明该字段（F-D3）
    import json
    from pathlib import Path
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "evidence.schema.json")
                        .read_text(encoding="utf-8"))
    assert "sufficiency" in schema["properties"], "sufficiency 机制必须入 schema"


def test_d07_strong_evidence_overrides_weak_insufficient(rde: RDE):
    """insufficient + 足量强证据 → supported（insufficient 不永久钉死状态）。"""
    rde.create_node(claim("claim-d7", [], [], [], work="proposed"))
    rde.append_evidence(_add(rde, "evidence-weak", supports=["claim-d7"],
                             sufficiency="insufficient"))
    assert _state(rde, "claim-d7") == "insufficient"
    rde.append_evidence(_add(rde, "evidence-strong", supports=["claim-d7"]))
    assert _state(rde, "claim-d7") == "supported"


# ---------------------------------------------------------------- D8 无删除路径

def test_d08_no_deletion_path_for_evidence(rde: RDE):
    """证据不存在删除 API；失效后节点与事件均可回查。"""
    rde.create_node(claim("claim-d8", [], [], [], work="proposed"))
    rde.append_evidence(_add(rde, "evidence-keep", supports=["claim-d8"]))
    rde.invalidate_evidence("evidence-keep", reason="测试")
    assert not hasattr(rde, "delete_evidence")
    assert not hasattr(rde.log, "delete")
    # 重放后证据节点仍在（只是 validity 变化）
    from core import replay
    st = replay(rde.log.events)
    assert st["nodes"]["evidence-keep"]["validity"] == "invalidated"


def test_d09_evidence_state_requires_evidential_driver(rde: RDE):
    """证据状态不能由逻辑事件驱动（逻辑/证据分离的对抗复核）。"""
    rde.create_node(claim("claim-d9", [], [], [], work="proposed"))
    with pytest.raises(IllegalTransition):
        rde.set_evidence_state("claim-d9", "supported", driven_by=["derivation_completed"])
    with pytest.raises(IllegalTransition):
        rde.set_evidence_state("claim-d9", "supported", driven_by=[])  # 空驱动
