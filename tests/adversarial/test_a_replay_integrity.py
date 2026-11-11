"""对抗审计 A — 事件与重放完整性（docs/event_sourcing.md）。

设计锚点：
- §1-2 事件日志 append-only，prev_hash/hash 哈希链防静默覆盖（原则 8）
- §4 重放确定性：seq 为唯一顺序权威；未知事件类型 → 失败；handler 纯函数
- 重放是第二重校验：绕过状态机写入的非法历史在重放时必须失败

发现编号见 reports/adversarial_audit.md（F-Axx）。
"""

from __future__ import annotations

import copy

import pytest

from core import RDE, EventLog, ChainBroken, ReplayError, IllegalTransition, RDEError
from core import replay, state_digest
from core.events import compute_event_hash, GENESIS

from conftest import base_node, claim, TS


def _chain(rde: RDE) -> list[dict]:
    return copy.deepcopy(rde.log.events)


def _rehash(event: dict, prev_hash: str) -> dict:
    """以攻击者身份重算合法哈希（模拟有写权限的篡改者）。"""
    event = dict(event)
    event["prev_hash"] = prev_hash
    h = compute_event_hash(event)
    event["event_id"] = f"evt-{h[:8]}"
    event["hash"] = h
    return event


@pytest.fixture()
def rde_with_history() -> RDE:
    r = RDE()
    r.create_node(base_node("definition-a", "definition", scope="全局", work="active"))
    r.create_node(base_node("assumption-a", "assumption", work="active"))
    r.create_node(claim("claim-a", [], [], ["assumption-a"], work="active"))
    r.refute("assumption-a", note="对抗审计夹具")
    return r


# ---------------------------------------------------------------- A1 篡改

def test_a01_tampered_mid_event_content_rejected(rde_with_history: RDE):
    """反例 A1：篡改中间事件内容 → 哈希链必须断。"""
    evs = _chain(rde_with_history)
    victim = evs[len(evs) // 2]
    victim["payload"] = {**victim.get("payload", {}), "_tampered": True}
    with pytest.raises(ChainBroken):
        EventLog(evs)
    with pytest.raises(ChainBroken):
        EventLog(evs, verify=False).verify_chain()
    # 事件 ID 由内容派生：篡改后 id 与内容不再对应
    recomputed = compute_event_hash(victim)
    assert victim["hash"] != recomputed


# ---------------------------------------------------------------- A2 顺序

def test_a02_reordered_events_rejected_by_chain(rde_with_history: RDE):
    """反例 A2：调换事件数组顺序 → 链衔接必须断（prev_hash 指向前序）。"""
    evs = _chain(rde_with_history)
    evs[0], evs[1] = evs[1], evs[0]
    with pytest.raises(ChainBroken):
        EventLog(evs)


def test_a02b_replay_order_independent_same_state(rde_with_history: RDE):
    """同一日志不同排列 → 重放仍一致（seq 是唯一顺序权威，event_sourcing §4）。"""
    evs = _chain(rde_with_history)
    shuffled = list(reversed(evs))
    assert state_digest(replay(shuffled)) == rde_with_history.digest()
    # 但该排列的 EventLog 视为断链：状态可重建 ≠ 日志完整（两件事分开）
    with pytest.raises(ChainBroken):
        EventLog(shuffled)


# ---------------------------------------------------------------- A3/A4 结构破坏

def test_a03_duplicate_seq_rejected(rde_with_history: RDE):
    """反例 A3：重复 seq → 重放必须失败。"""
    evs = _chain(rde_with_history)
    evs[1]["seq"] = evs[0]["seq"]
    with pytest.raises(ReplayError, match="seq 不连续"):
        replay(evs)


def test_a04_deleted_middle_event_rejected(rde_with_history: RDE):
    """反例 A4：删除中间事件 → 链与重放双双失败（历史不可被静默删除）。"""
    evs = _chain(rde_with_history)
    evs.pop(0)
    with pytest.raises(ChainBroken):
        EventLog(evs)
    with pytest.raises(ReplayError, match="seq 不连续"):
        replay(evs)


def test_a05_modified_prev_hash_rejected(rde_with_history: RDE):
    """反例 A5：只改 prev_hash（不改内容）→ 链衔接断。"""
    evs = _chain(rde_with_history)
    evs[1]["prev_hash"] = "f" * 64
    with pytest.raises(ChainBroken):
        EventLog(evs)


# ---------------------------------------------------------------- A6/A7 语义层

def test_a06_unknown_event_fails_replay_even_with_valid_hash(rde_with_history: RDE):
    """反例 A6：插入哈希完全合法的未知事件 → 链通过（链≠语义），重放必须失败。"""
    evs = _chain(rde_with_history)
    unknown = {
        "seq": len(evs), "type": "totally_mystery", "timestamp": TS,
        "actor": "system", "target": ["claim-a"], "payload": {},
    }
    evs.append(_rehash(unknown, evs[-1]["hash"]))
    assert EventLog(evs).verify_chain() is True        # 完整性通过
    with pytest.raises(ReplayError, match="未知事件类型"):
        replay(evs)                                     # 语义层拦截


def test_a07_illegal_transition_injection_fails_replay(rde_with_history: RDE):
    """反例 A7：注入哈希合法的非法状态转换（proposed→completed）→ 重放必须失败。"""
    evs = _chain(rde_with_history)
    bad = {
        "seq": len(evs), "type": "work_state_changed", "timestamp": TS,
        "actor": "human", "target": ["claim-a"],
        "payload": {"from": "proposed", "to": "completed"},
    }
    evs.append(_rehash(bad, evs[-1]["hash"]))
    assert EventLog(evs).verify_chain() is True        # 链不管语义（按设计）
    with pytest.raises((IllegalTransition, ReplayError)):
        replay(evs)


def test_a07b_cross_dimension_injection_fails_replay(rde_with_history: RDE):
    """注入伪造的经验轨语义升级（empirical route）→ 重放必须失败（边界 4/5）。"""
    evs = _chain(rde_with_history)
    bad = {
        "seq": len(evs), "type": "proposition_state_changed", "timestamp": TS,
        "actor": "agent:x", "target": ["claim-a"],
        "payload": {"from": "unknown", "to": "true_in_scope",
                    "justification": {"route": "empirical", "evidence": ["evidence-z"]}},
    }
    evs.append(_rehash(bad, evs[-1]["hash"]))
    with pytest.raises((IllegalTransition, ReplayError)):
        replay(evs)


# ---------------------------------------------------------------- A8/A9/A10 入口分层

def test_a08_tampered_log_rejected_at_all_entry_points(rde_with_history: RDE):
    """所有载入入口都必须校验链：EventLog 构造、RDE 构造、RDE.restore。"""
    evs = _chain(rde_with_history)
    evs[0]["payload"]["node"]["content"] = "改写"
    with pytest.raises(ChainBroken):
        EventLog(evs)
    with pytest.raises(ChainBroken):
        RDE(evs)
    # RDE(list) 也走 EventLog 默认 verify=True
    with pytest.raises(ChainBroken):
        RDE(EventLog(evs, verify=False))


def test_a09_rde_restore_verifies_chain(tmp_path, rde_with_history: RDE):
    path = tmp_path / "ev.jsonl"
    rde_with_history.save(path)
    # 磁盘上改一行
    lines = path.read_text(encoding="utf-8").splitlines()
    import json
    obj = json.loads(lines[1])
    obj["payload"]["node"]["content"] = "磁盘篡改"
    lines[1] = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    from core.errors import ChainBroken as CB
    with pytest.raises(CB):
        RDE.restore(path)


def test_a10_replay_layer_documented_not_chain_checked(rde_with_history: RDE):
    """分层事实记录（F-A6）：裸 replay() 不校验链、只保证确定性；
    链校验职责在 EventLog/RDE 入口。两层各自职责必须被显式认知。"""
    evs = _chain(rde_with_history)
    evs[0]["payload"]["node"]["content"] = "裸改"
    # 裸 replay：不查链，但同一(被改)日志重放仍自洽确定
    d1 = state_digest(replay(evs))
    d2 = state_digest(replay(list(reversed(evs))))
    assert d1 == d2, "裸重放仍必须是确定性的（确定性 ≠ 完整性）"
    # 入口层必查
    with pytest.raises(ChainBroken):
        EventLog(evs)
    # 结论：直接使用裸 replay() 绕过完整性校验是可能的 —— 用法约束，见审计报告 F-A6


def test_a11_genesis_chain_head(rde_with_history: RDE):
    """首事件锚定 GENESIS；链头可复算。"""
    evs = rde_with_history.log.events
    assert evs[0]["prev_hash"] == GENESIS
    assert rde_with_history.log.verify_chain() is True
    assert rde_with_history.log.chain_head() == evs[-1]["hash"]
