"""对抗审计 F — 图结构（docs/graph_semantics.md、§3.2 边语义）。"""

from __future__ import annotations

import time

import pytest

from core import RDE
from core.errors import ValidationError
from core.graph import validate_edge
from core.dependency_analysis import _route_status

from conftest import base_node, claim, derivation, TS


def edge(eid, etype, category, premises, conclusions, validity="active"):
    return {"id": eid, "type": etype, "category": category, "premises": premises,
            "conclusions": conclusions, "created_at": TS,
            "source": {"origin": "human"}, "scope": "示例范围", "validity": validity}


# ---------------------------------------------------------------- F1 超边多层

def test_f01_hyperedge_multilayer_propagation(rde: RDE):
    """两前提汇合 → 两结论，再向下一层传播（多层依赖）。"""
    rde.create_node(base_node("definition-x", "definition", scope="全局", work="active"))
    rde.create_node(base_node("assumption-y", "assumption", work="active"))
    rde.create_node(claim("claim-p", [], [], [], work="proposed"))
    rde.create_node(claim("claim-q", [], [], [], work="proposed"))
    rde.create_node(claim("claim-r", [], [], [], work="proposed"))
    # 层 1：{x, y} ⊢ {p, q}
    rde.create_edge(edge("edge-l1", "entails", "logical",
                         ["definition-x", "assumption-y"], ["claim-p", "claim-q"]))
    # 层 2：p → r
    rde.create_edge(edge("edge-l2", "entails", "logical", ["claim-p"], ["claim-r"]))
    report = rde.impact({"assumption-y": "refuted"})
    affected = set(report["directly_affected"])
    assert {"claim-p", "claim-q"} <= affected, "超边两个结论都应受影响"
    assert "claim-r" in affected, "第二层下游也应受影响"
    assert "definition-x" not in affected, "未变化的兄弟前提不应入列"


# ---------------------------------------------------------------- F2/F3 循环

def test_f02_cycle_terminates_and_is_reported(rde: RDE):
    """循环依赖（A↔B）：传播必须终止，且双方都在视野内（正确性优先，不挂死）。"""
    rde.create_node(base_node("assumption-p", "assumption", work="active"))
    rde.create_node(base_node("assumption-q", "assumption", work="active"))
    rde.create_edge(edge("edge-c1", "depends_on", "logical", ["assumption-q"], ["assumption-p"]))
    rde.create_edge(edge("edge-c2", "depends_on", "logical", ["assumption-p"], ["assumption-q"]))
    t0 = time.monotonic()
    report = rde.impact({"assumption-p": "refuted"})
    assert time.monotonic() - t0 < 1.0, "传播必须在有界时间内终止"
    assert "assumption-q" in report["directly_affected"]
    # 已知观察项 F-F3：当前不产生『检测到环』的显式警告（设计未承诺 → 记录为观察）


def test_f03_self_loop_terminates(rde: RDE):
    rde.create_node(base_node("assumption-s", "assumption", work="active"))
    rde.create_edge(edge("edge-self", "depends_on", "logical",
                         ["assumption-s"], ["assumption-s"]))
    t0 = time.monotonic()
    report = rde.impact({"assumption-s": "refuted"})
    assert time.monotonic() - t0 < 1.0
    # 自身不出现在自己的 downstream（起点排除）
    assert "assumption-s" not in report["directly_affected"]


# ---------------------------------------------------------------- F4 重复关系

def test_f04_duplicate_edge_id_rejected(rde: RDE):
    rde.create_node(base_node("assumption-a", "assumption", work="active"))
    rde.create_node(base_node("assumption-b", "assumption", work="active"))
    rde.create_edge(edge("edge-dup", "depends_on", "logical", ["assumption-a"], ["assumption-b"]))
    n_before, digest_before = len(rde.log), rde.digest()
    with pytest.raises(ValidationError, match="已存在"):
        rde.create_edge(edge("edge-dup", "depends_on", "logical",
                             ["assumption-b"], ["assumption-a"]))
    # F-A8 不变量：被拒绝的创建*不得*留下任何事件 —— 日志长度、状态、重放能力都不变。
    # （修复前 _emit 先 append 再 apply，失败会毒化引擎自身日志。）
    assert len(rde.log) == n_before, "失败的创建不得写入事件"
    assert rde.digest() == digest_before
    from core import replay
    assert replay(rde.log.events) is not None, "日志必须仍可重放"


def test_f04b_content_duplicate_edges_allowed_documented(rde: RDE):
    """F-F2（观察项）：内容完全相同但 ID 不同的重复关系当前被允许（仅 ID 唯一）。
    无去重语义承诺 → 固化事实，供研究者裁决是否需要内容指纹。"""
    rde.create_node(base_node("assumption-a", "assumption", work="active"))
    rde.create_node(base_node("assumption-b", "assumption", work="active"))
    rde.create_edge(edge("edge-dup-1", "depends_on", "logical",
                         ["assumption-a"], ["assumption-b"]))
    rde.create_edge(edge("edge-dup-2", "depends_on", "logical",
                         ["assumption-a"], ["assumption-b"]))
    assert len([e for e in rde.graph.edges.values() if e["type"] == "depends_on"]) == 2


# ---------------------------------------------------------------- F5/F6 引用与语义

def test_f05_nonexistent_reference_rejected(rde: RDE):
    rde.create_node(base_node("assumption-a", "assumption", work="active"))
    with pytest.raises(ValidationError, match="不存在"):
        rde.create_edge(edge("edge-ghost", "depends_on", "logical",
                             ["assumption-a"], ["assumption-nope"]))
    # 边端点也不能为空
    with pytest.raises(ValidationError):
        validate_edge(edge("edge-empty", "depends_on", "logical", [], ["assumption-a"]))


def test_f06_type_category_mixing_rejected(rde: RDE):
    """关系类型与类别混用必须被拒（逻辑/证据分离的结构闸门）。"""
    with pytest.raises(ValidationError, match="类别不一致"):
        validate_edge(edge("edge-mix-1", "entails", "evidential", ["a"], ["b"]))
    with pytest.raises(ValidationError, match="类别不一致"):
        validate_edge(edge("edge-mix-2", "supports", "logical", ["a"], ["b"]))
    with pytest.raises(ValidationError, match="未知边类型"):
        validate_edge(edge("edge-mix-3", "causes", "logical", ["a"], ["b"]))


def test_f07_archived_premise_breaks_route_and_stays_resolvable(rde: RDE):
    """节点归档：不是删除 —— 仍可解析引用，但路线判 broken。"""
    rde.create_node(base_node("assumption-old", "assumption", work="active"))
    rde.create_node(claim("claim-f7", ["derivation-f7"], [], ["assumption-old"]))
    rde.start_derivation(derivation("derivation-f7", ["assumption-old"], ["claim-f7"]))
    rde.set_work_state("assumption-old", "archived", reason="路线剪枝")
    # 仍可解析（无删除）
    assert rde.graph.require("assumption-old")["work_state"] == "archived"
    # 路线 broken → 命题失去支撑
    st = _route_status(rde.graph.require("derivation-f7"), rde.graph, set())
    assert st == "broken", "归档的前提不得继续支撑路线"


def test_f07b_invalid_edge_type_direction_semantics(rde: RDE):
    """depends_on 的方向语义：依赖者是 premises、基础是 conclusions →
    基础变化向『依赖者』传播，而不是反向。"""
    rde.create_node(base_node("definition-base", "definition", scope="全局", work="active"))
    rde.create_node(base_node("assumption-user", "assumption", work="active"))
    rde.create_edge(edge("edge-dir", "depends_on", "logical",
                         ["assumption-user"], ["definition-base"]))
    report = rde.impact({"definition-base": "modified"})
    assert "assumption-user" in report["directly_affected"]
    # 反向（基础依赖依赖者）不应因这条边产生
    report2 = rde.impact({"assumption-user": "modified"})
    assert "definition-base" not in report2["directly_affected"]


def test_f08_withdrawn_edge_not_traversed(rde: RDE):
    rde.create_node(base_node("assumption-k", "assumption", work="active"))
    rde.create_node(base_node("question-q", "question", work="active"))
    rde.create_edge(edge("edge-b", "blocks", "managerial",
                         ["assumption-k"], ["question-q"]))
    assert "question-q" in rde.impact({"assumption-k": "refuted"})["directly_affected"]
    rde._emit("edge_validity_changed", actor="system", target=["edge-b"],
              payload={"edge_id": "edge-b", "validity": "withdrawn"})
    assert rde.graph.get_edge("edge-b") is not None, "失效边保留（原则 8）"
    assert "question-q" not in rde.impact({"assumption-k": "refuted"})["directly_affected"]


def test_f09_no_deletion_apis_anywhere(rde: RDE):
    """全局：引擎与日志不提供删除 API（历史不可被静默覆盖）。"""
    for name in ("delete_node", "remove_node", "delete_edge", "remove_edge",
                 "drop_event", "purge"):
        assert not hasattr(rde, name), f"{name} 不应存在"
    for name in ("delete", "remove", "purge", "truncate"):
        assert not hasattr(rde.log, name), f"EventLog.{name} 不应存在"
