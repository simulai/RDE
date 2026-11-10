"""对抗审计 B — 版本与历史（docs/event_sourcing.md §5.1、graph_semantics.md §5）。

设计锚点：
- 验收标准 2：修改定义不会静默改变旧版本；时间点可回溯
- 验收标准 8：所有研究决策可回溯
- 旧版本边失效不删除；分叉互不污染

发现编号见 reports/adversarial_audit.md（F-Bxx）。
"""

from __future__ import annotations

import copy

import pytest

from core import RDE, replay, state_digest
from core.versioning import version_chain

from conftest import base_node, claim, TS


def _derivation(did, premises, concludes, content="占位证明", status="draft"):
    return {"id": did, "type": "derivation", "version": 1, "created_at": TS,
            "source": {"origin": "human"}, "scope": "示例范围", "content": content,
            "premises": premises, "concludes": concludes, "track": "mathematical",
            "status": status, "work_state": "active"}


@pytest.fixture()
def versioned(rde: RDE) -> RDE:
    """Definition v1 + 引用它的旧 Derivation + 引用它的 Claim。"""
    rde.create_node(base_node("definition-d1", "definition", content="v1 原文", scope="全局",
                              work="active"))
    rde.create_node(claim("claim-v", ["derivation-old"], ["definition-d1"], [], work="active"))
    rde.start_derivation(_derivation("derivation-old", ["definition-d1"], ["claim-v"],
                                     content="基于 v1 的证明", status="completed"))
    return rde


# ---------------------------------------------------------------- B1 修订

def test_b01_revision_preserves_v1_and_old_derivation(versioned: RDE):
    """旧 Derivation 不被静默改写；v1 内容可精确回溯。"""
    v1_node = copy.deepcopy(versioned.graph.require("derivation-old"))
    seq_before = len(versioned.log) - 1
    digest_before = versioned.digest()

    versioned.revise_node("definition-d1", {"content": "v2 修订原文"}, reason="对抗审计")

    # (1) 旧证明节点逐字节未变
    assert versioned.graph.require("derivation-old") == v1_node
    # (2) 时间点回溯得到修订前状态（含 v1 内容）
    past = versioned.state_at(seq_before)
    assert state_digest(past) == digest_before
    assert past["nodes"]["definition-d1"]["content"] == "v1 原文"
    # (3) 当前版本 = v2，历史中保留 v1 快照
    assert versioned.graph.require("definition-d1")["version"] == 2
    history = versioned.state["history"]["definition-d1"]
    assert history[-1]["content"] == "v1 原文"
    assert [h["version"] for h in version_chain(history, versioned.graph.require("definition-d1"))] == [1, 2]


def test_b02_revision_emits_impact_flagging_old_route(versioned: RDE):
    """修订时的检测通道必须工作：影响报告事件把引用旧版本的路线标为需复核。"""
    versioned.revise_node("definition-d1", {"content": "v2"}, reason="对抗审计")
    reports = versioned.log.by_type("impact_report_generated")
    assert reports, "基础节点修改必须产生影响报告（原则 7）"
    last = reports[-1]["payload"]
    assert last["change"]["node"] == "definition-d1"
    deriv_entry = [e for e in last["propagated"] if e["node"] == "derivation-old"]
    assert deriv_entry and deriv_entry[0]["status"] in ("broken", "affected"), \
        "引用被修订定义的路线必须进入复核视野"


def test_b03_version_pin_gap_is_observable(versioned: RDE):
    """F-B1（已知缺口，Q-007/R-017）：路线前提按 ID 解析到*当前*版本，
    无法在路线层表达"我绑定 v1"。本测试固化当前可观察事实，不把它当作正确性：

    1) claim.definition_versions 保持 [v1]（这是正确的：命题当时绑定 v1）；
    2) 但路线评估读到的是当前节点（v2）——二者出现漂移；
    3) 漂移在修订当刻由影响报告（b02）标记，修订之后无法再从路线自身重建当次判定。
    """
    versioned.revise_node("definition-d1", {"content": "v2"}, reason="对抗审计")
    claim_node = versioned.graph.require("claim-v")
    current_def = versioned.graph.require("definition-d1")
    # 事实 1：命题的版本绑定未被静默改写
    assert claim_node["definition_versions"] == [{"id": "definition-d1", "version": 1}]
    # 事实 2：图中该 ID 当前解析为 v2 → 漂移存在
    assert current_def["version"] == 2
    assert claim_node["definition_versions"][0]["version"] != current_def["version"]
    # 事实 3：无 delta 重查路线 → 按当前(v2)节点判为 intact（无法表达 v1 绑定）
    from core.dependency_analysis import _route_status
    status = _route_status(versioned.graph.require("derivation-old"), versioned.graph, set())
    assert status == "intact", "当前实现按当前版本解析（该事实本身是缺口 F-B1，待研究者裁决）"


# ---------------------------------------------------------------- B4 分叉

def test_b04_fork_isolation_bidirectional(versioned: RDE):
    """分叉后双向互不污染：改原不影响分叉，改分叉不影响原。"""
    versioned.fork_definition("definition-d1", "definition-d1-varB",
                              changes={"content": "分叉原文", "scope": "分叉语境"})
    versioned.revise_node("definition-d1-varB", {"content": "分叉 v2"}, reason="对抗审计")
    versioned.revise_node("definition-d1", {"content": "原线 v2"}, reason="对抗审计")
    orig = versioned.graph.require("definition-d1")
    fork = versioned.graph.require("definition-d1-varB")
    assert orig["content"] == "原线 v2" and orig["version"] == 2
    assert fork["content"] == "分叉 v2" and fork["version"] == 2
    assert fork["fork_of"] == "definition-d1"
    # 分叉的历史中没有原线的内容，反之亦然
    assert all(h["content"] != "原线 v2" for h in versioned.state["history"].get("definition-d1-varB", []))
    assert all(h["content"] != "分叉 v2" for h in versioned.state["history"].get("definition-d1", []))


def test_b05_fork_has_own_event_history(versioned: RDE):
    versioned.fork_definition("definition-d1", "definition-d1-varB", changes={"content": "x"})
    forks = versioned.state["forks"]
    assert any(f["original"] == "definition-d1" and f["fork"] == "definition-d1-varB"
               for f in forks)
    # 原对象 v1 不因分叉而变化
    assert versioned.graph.require("definition-d1")["version"] == 1


# ---------------------------------------------------------------- B6 边失效不删除

def test_b06_invalid_edge_retained_but_not_traversed(versioned: RDE):
    """旧版本边：失效后仍可读（历史），但不参与传播。"""
    versioned.create_node(base_node("question-q", "question", work="active"))
    versioned.create_edge({
        "id": "edge-old-link", "type": "motivates", "category": "managerial",
        "premises": ["definition-d1"], "conclusions": ["question-q"],
        "created_at": TS, "source": {"origin": "human"}, "scope": "示例范围",
        "validity": "active",
    })
    report = versioned.impact({"definition-d1": "modified"})
    assert "question-q" in report["directly_affected"]
    # 失效
    versioned._emit("edge_validity_changed", actor="system", target=["edge-old-link"],
                    payload={"edge_id": "edge-old-link", "validity": "superseded"})
    edge = versioned.graph.get_edge("edge-old-link")
    assert edge is not None, "历史边不得被删除（原则 8）"
    assert edge["validity"] == "superseded"
    report2 = versioned.impact({"definition-d1": "modified"})
    assert "question-q" not in report2["directly_affected"], "失效边不得再传播"


# ---------------------------------------------------------------- B7 多次修订链

def test_b07_multi_revision_history_exact(versioned: RDE):
    """每次修订后的状态，都能在对应 seq 时间点精确重建。"""
    anchors = []
    for i in range(3):
        anchors.append((len(versioned.log) - 1, versioned.digest()))
        versioned.revise_node("definition-d1", {"content": f"内容 v{i+2}"}, reason=f"r{i}")
    anchors.append((len(versioned.log) - 1, versioned.digest()))
    for seq, d in anchors:
        assert state_digest(versioned.state_at(seq)) == d, f"seq={seq} 回溯不一致"
    # 历史栈完整（被取代版本按序保留，当前版本不在历史栈内）
    history = versioned.state["history"]["definition-d1"]
    assert [h["content"] for h in history] == ["v1 原文", "内容 v2", "内容 v3"]
    assert versioned.graph.require("definition-d1")["content"] == "内容 v4"
