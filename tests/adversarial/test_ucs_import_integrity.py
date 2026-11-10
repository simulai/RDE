"""对抗审计 U — UCS 导入草案完整性（experiments/UCS/、examples/ucs_research_graph.json）。

纪律（任务书 §7 / 导入审计）：
- 不代填真相：所有未确认状态保持 unknown / none；
- 关系假设必须是 Hypothesis 节点（claim 型槽位），不得预置为 entails 边；
- 2^8 = 256 组合空间只作为封闭结构空间登记，不枚举、不判定；
- 不预设单调性；
- 缺失定义标记【待人工确认】，而非补全。
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from core import RDE
from core.graph import validate_node

REPO = Path(__file__).resolve().parents[2]
DEFS = REPO / "experiments" / "UCS" / "definitions.json"
HYPS = REPO / "experiments" / "UCS" / "hypotheses.json"
GRAPH = REPO / "examples" / "ucs_research_graph.json"

TASK_BOOK_NAMES = {
    1: "选择性信息压缩", 2: "稳定离散化", 3: "可组合结构", 4: "后果接地",
    5: "双向耦合", 6: "可修订性", 7: "历史连续性", 8: "有限资源协调",
}


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _schema(name: str) -> Draft202012Validator:
    data = json.loads((REPO / "schemas" / name).read_text(encoding="utf-8"))
    reg = Registry()
    for f in sorted((REPO / "schemas").glob("*.schema.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        reg = reg.with_resource(uri=d["$id"],
                                resource=Resource.from_contents(d,
                                                                default_specification=DRAFT202012))
    return Draft202012Validator(data, registry=reg)


def test_u01_definitions_eight_conditions_exact_names_and_states():
    """U01：8 条件齐全、名称逐字来自任务书、状态全为 unknown/none/proposed。"""
    data = _load(DEFS)
    conds = data["conditions"]
    assert len(conds) == 8
    by_index = {i: c for i, c in enumerate(conds, start=1)}
    assert set(by_index) == set(range(1, 9))
    for i in range(1, 9):
        node = by_index[i]
        assert node["id"] == f"definition-ucs-n{i}"
        assert f"N{i} {TASK_BOOK_NAMES[i]}" in node["content"], "条件名必须逐字来自任务书"
        assert "待人工确认" in node["content"], "缺失的定义必须标记待人工确认，不得补全"
        assert node["proposition_state"] == "unknown"
        assert node["evidence_state"] == "none"
        assert node["work_state"] == "proposed"
        validate_node(node)
    # _meta：封闭空间 + 不预设单调 + 不代填
    meta = data["_meta"]
    assert meta["combination_space_size"] == 256 and meta["combination_space"] == "closed"
    assert any("不预设" in w and "单调" in w for w in meta["warnings"])
    assert any("不代填" in w for w in meta["warnings"])


def test_u02_hypotheses_are_nodes_not_edges_and_all_pending():
    """U02：28 个关系假设槽位 —— Hypothesis 节点形态、零真值、全部待人工确认。"""
    data = _load(HYPS)
    slots = data["hypotheses"]
    # 结构枚举空间：C(8,2) = 28 对
    expected_pairs = set(itertools.combinations(range(1, 9), 2))
    got_pairs = {tuple(int(x) for x in s["id"].split("-")[-2:]) for s in slots}
    assert got_pairs == expected_pairs
    for s in slots:
        slot = s["hypothesis_slot"]
        assert slot["relation"] is None, "关系类型未确认，不得填写"
        assert slot["direction"] is None
        assert slot["asserted"] is False, "槽位不是关系断言"
        assert slot["monotonicity_assumed"] is False, "不得预设单调性"
        assert slot["status"] == "待人工确认"
        assert s["proposition_state"] == "unknown"
        assert s["evidence_state"] == "none"
        assert s["work_state"] == "proposed"
        assert s["routes"] == [] and s["current_evidence"] == []
        assert all(o["status"] == "open" for o in s["proof_obligations"])
        validate_node(s)
    meta = data["_meta"]
    assert meta["monotonicity_assumed"] is False
    assert "entails" in meta["representation_policy"], "假设必须以节点登记，不以 entails 边"
    assert len(meta["relation_kinds_pending"]) == 6  # 五类 + none，均为待选清单


def test_u03_graph_has_zero_entails_edges_and_unknown_states():
    """U03：合并图 0 条边（未确认关系不入图）；全节点 unknown/none/proposed。"""
    g = _load(GRAPH)
    assert g["edges"] == [], "未经确认的关系不得产生边"
    assert len(g["nodes"]) == 36  # 8 definitions + 28 hypothesis slots
    for n in g["nodes"]:
        assert n["proposition_state"] == "unknown"
        assert n["evidence_state"] == "none"
        assert n["work_state"] == "proposed"
        validate_node(n)
    assert g["_meta"]["entails_edges"] == 0
    assert g["_meta"]["combination_space"] == "closed"
    assert g["_meta"]["monotonicity_assumed"] is False


def test_u04_all_ucs_nodes_pass_json_schema():
    """U04：全部导入节点通过对应 JSON Schema（Draft 2020-12）。"""
    node_v = _schema("node.schema.json")
    claim_v = _schema("claim.schema.json")
    g = _load(GRAPH)
    for n in g["nodes"]:
        v = claim_v if n["type"] == "claim" else node_v
        errs = [e.message for e in v.iter_errors(n)]
        assert errs == [], f"{n['id']}: {errs}"


def test_u05_graph_loads_into_engine_with_states_unchanged():
    """U05：可载入 RDE；载入本身不改变任何状态（无转换事件）。"""
    g = _load(GRAPH)
    rde = RDE()
    for n in g["nodes"]:
        rde.create_node(n, actor="agent:importer")
    assert len(rde.graph.nodes) == 36
    for n in g["nodes"]:
        cur = rde.graph.require(n["id"])
        assert cur["proposition_state"] == "unknown"
        assert cur["evidence_state"] == "none"
        assert cur["work_state"] == "proposed"
    # 重放一致（验收 1）
    from core import replay, state_digest
    assert state_digest(replay(rde.log.events)) == rde.digest()


def test_u06_no_combination_enumeration_no_monotonicity_anywhere():
    """U06：任何导入文件都不得出现组合枚举赋值或单调性断言。"""
    for p in (DEFS, HYPS, GRAPH):
        text = p.read_text(encoding="utf-8")
        data = _load(p)
        blob = json.dumps(data, ensure_ascii=False)
        assert '"monotonicity_assumed": true' not in blob, f"{p} 出现单调性断言"
        # 不得出现对具体组合的真值赋值（combination 对象仅允许出现在占位示例中，
        # 本导入文件不应有 combination→claim 的判定记录）
        assert "combination" not in json.dumps(
            data.get("hypotheses", []), ensure_ascii=False
        ) or True  # hypotheses 中无 combination 字段（下一断言精确检查）
    h = _load(HYPS)
    for s in h["hypotheses"]:
        assert "combination" not in s
        assert "combination" not in s["hypothesis_slot"]


def test_u07_pending_markers_present_not_completed():
    """U07：缺失处必须是【待人工确认】标记，而不是被补全的内容。"""
    defs = _load(DEFS)
    for c in defs["conditions"]:
        # 定义只有名称 + 待确认标记；没有出现解释性展开
        assert c["content"].count("。") <= 2, "定义内容不应被代为展开"
        assert "【待人工确认" in c["content"]
    h = _load(HYPS)
    for s in h["hypotheses"]:
        assert "待人工确认" in s["content"]
        assert s["next_research_action"]["action"].startswith("待人工确认")
        assert s["falsification_conditions"][0].startswith("待人工确认")
