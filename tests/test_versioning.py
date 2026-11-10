"""版本测试：定义修改不静默改变旧版本、时间点回溯、定义分叉、防状态夹带。

对应验收标准 2、任务书 M6（Fork Definition）。
"""

from __future__ import annotations

import pytest

from core import RDE, IllegalTransition, replay, state_digest
from core.errors import ValidationError
from core.versioning import bump_version, fork_node, assert_no_silent_overwrite

from conftest import base_node, claim, TS


def test_definition_change_preserves_old_version(scenario: RDE):
    """验收标准 2：修改定义不会静默改变旧版本。"""
    seq_before = len(scenario.log) - 1
    digest_before = scenario.digest()
    state_at_before = scenario.state_at(seq_before)
    snapshot_v1 = dict(scenario.graph.require("definition-d1"))

    scenario.revise_node("definition-d1", {"content": "定义 D1（修订 v2）"},
                         reason="测试：定义修订")
    new = scenario.graph.require("definition-d1")
    assert new["version"] == 2
    assert new["content"].endswith("（修订 v2）")
    # 旧版本快照逐字段未被改动
    assert snapshot_v1["version"] == 1
    assert snapshot_v1["content"] == "definition-d1"
    history = scenario.state["history"]["definition-d1"]
    assert history[-1] == snapshot_v1
    # 时间点重建得到修改前的完全一致状态
    assert state_digest(state_at_before) == digest_before


def test_version_rollback_rejected(scenario: RDE):
    old = scenario.graph.require("definition-d1")
    with pytest.raises(ValidationError, match="版本回退|不可变"):
        bump_version(old, {"version": 0})
    with pytest.raises(ValidationError, match="不可变字段"):
        bump_version(old, {"id": "definition-evil"})


def test_state_field_smuggling_rejected(scenario: RDE):
    """禁止通过内容修订夹带状态字段（防绕过状态机非法升级）。"""
    with pytest.raises(ValidationError, match="状态字段"):
        bump_version(scenario.graph.require("claim-c1"),
                     {"proposition_state": "true_in_scope"})
    with pytest.raises(ValidationError, match="状态字段"):
        scenario.revise_node("claim-c1", {"work_state": "completed"})


def test_definition_fork_keeps_original(scenario: RDE):
    """M6 Fork Definition：原对象不动，新 ID 独立演化。"""
    fork = scenario.fork_definition(
        "definition-d1", "definition-d1-varB",
        changes={"content": "定义 D1 的分叉变体 B", "scope": "分叉语境 B"})
    original = scenario.graph.require("definition-d1")
    assert fork["fork_of"] == "definition-d1"
    assert fork["version"] == 1
    assert original["version"] == 1
    assert original["content"] == "definition-d1"
    # 分叉事件可回溯
    forks = scenario.state["forks"]
    assert any(f["original"] == "definition-d1" and f["fork"] == "definition-d1-varB"
               for f in forks)
    # 原节点与分叉节点同时存在（历史不被覆盖）
    assert scenario.graph.get("definition-d1") is not None
    assert scenario.graph.get("definition-d1-varB") is not None


def test_fork_id_prefix_rule():
    with pytest.raises(ValidationError, match="前缀"):
        fork_node(base_node("definition-a", "definition"), "assumption-a", {})


def test_replay_after_revisions_matches_live_state(scenario: RDE):
    scenario.revise_node("definition-d1", {"content": "v2"}, reason="test")
    scenario.revise_node("claim-c1", {"content": "命题修订 v2"}, reason="test")
    rebuilt = replay(scenario.log.events)
    assert state_digest(rebuilt) == scenario.digest()


def test_no_silent_overwrite_guard():
    old = base_node("definition-z", "definition")
    new = bump_version(old, {"content": "changed"})
    assert_no_silent_overwrite(old, new)
    with pytest.raises(ValidationError):
        assert_no_silent_overwrite(old, dict(new, version=1))
