"""版本与分叉（docs/event_sourcing.md §5.1、任务书 M6）。

原则（验收标准 2）：修改定义不会静默改变旧版本 —— 旧版本快照必须保持逐字节不变；
新版本 = version + 1 的新记录；分叉 = 新 ID + fork_of 关系。
"""

from __future__ import annotations

import copy
from typing import Any

from ..errors import ValidationError

_IMMUTABLE_FIELDS = ("id", "type", "version", "created_at")


def bump_version(node: dict, changes: dict, *, forbid_state_fields: bool = True) -> dict:
    """由当前版本节点构造下一版本（纯函数，不修改输入）。

    forbid_state_fields=True：禁止通过通用内容修改夹带状态字段 ——
    状态变化必须走显式 set_*_state 接口（状态机检查，防非法升级）。
    """
    state_fields = {"proposition_state", "evidence_state", "work_state"}
    if forbid_state_fields and state_fields & set(changes):
        illegal = sorted(state_fields & set(changes))
        raise ValidationError(
            f"内容修改不得夹带状态字段 {illegal}；请使用显式状态转换接口（状态机校验）"
        )
    overlap = set(_IMMUTABLE_FIELDS) & set(changes)
    if overlap:
        raise ValidationError(f"不可变字段不得修改: {sorted(overlap)}")
    new_node = copy.deepcopy(node)
    new_node.update(copy.deepcopy(changes))
    new_node["version"] = node["version"] + 1
    return new_node


def fork_node(node: dict, new_id: str, changes: dict | None = None) -> dict:
    """Fork Definition（M6）：产生新 ID 的分叉对象，原对象不动。"""
    if new_id == node["id"]:
        raise ValidationError("fork 的新 ID 不得与原 ID 相同")
    if not new_id.split("-")[0] == node["type"]:
        raise ValidationError(f"fork 新 ID 前缀应为 {node['type']}-（ID 规则，graph_semantics §1）")
    forked = copy.deepcopy(node)
    forked["id"] = new_id
    forked["version"] = 1
    forked["fork_of"] = node["id"]
    if changes:
        state_fields = {"proposition_state", "evidence_state", "work_state"}
        if state_fields & set(changes):
            raise ValidationError("fork 变更不得夹带状态字段")
        forked.update(copy.deepcopy(changes))
    return forked


def assert_no_silent_overwrite(old: dict, new: dict) -> None:
    """结构保证：新版本严格递增，旧版本快照未被就地修改。"""
    if new["id"] != old["id"]:
        raise ValidationError("比较的必须是同一对象的两个版本")
    if new["version"] <= old["version"]:
        raise ValidationError(
            f"版本回退被拒绝: {old['id']} v{old['version']} → v{new['version']}"
        )
    for f in _IMMUTABLE_FIELDS:
        if f in ("version",):
            continue
        if old.get(f) != new.get(f):
            raise ValidationError(f"不可变字段被改写: {f}")


def version_chain(history: list[dict], current: dict) -> list[dict]:
    """按时间顺序返回 [v1, v2, ..., current]（旧在前）。"""
    return list(history) + [current]
