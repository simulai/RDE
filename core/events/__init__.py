"""Append-only 事件日志（docs/event_sourcing.md）。

- 唯一真相源：没有 update/delete API；历史修改只会断链（原则 8）。
- seq 决定重放顺序；timestamp 仅展示用（并发确定性）。
- prev_hash/hash 形成 SHA-256 哈希链；event_id 由内容哈希派生（重放确定性）。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from ..errors import ChainBroken

GENESIS = "GENESIS"
_HASH_LEN = 64

# 事件顺序参与哈希的字段（除 prev_hash 外）
_HASHED_FIELDS = ("seq", "type", "timestamp", "actor", "target", "payload")


def canonical(obj: Any) -> str:
    """规范化 JSON 序列化：键排序、无空白、UTF-8 保留。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_event_hash(event: dict) -> str:
    """计算事件哈希（输入事件可含 prev_hash，但不得含 hash/event_id）。"""
    basis = {"prev_hash": event.get("prev_hash", GENESIS)}
    for f in _HASHED_FIELDS:
        basis[f] = event[f]
    return hashlib.sha256(canonical(basis).encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class EventLog:
    """不可变事件序列的内存容器 + JSONL 持久化。"""

    def __init__(self, events: Iterable[dict] | None = None, *, verify: bool = True):
        self._events: list[dict] = []
        if events:
            for ev in events:
                self._events.append(dict(ev))
            if verify:
                self.verify_chain()

    # ------------------------------------------------------------- 写入
    def append(
        self,
        type: str,
        *,
        actor: str,
        target: list[str],
        payload: dict,
        timestamp: str | None = None,
    ) -> dict:
        """追加一条事件并返回它。不提供修改/删除历史的接口。"""
        if not target:
            raise ValueError("事件必须至少有一个 target")
        prev_hash = self._events[-1]["hash"] if self._events else GENESIS
        event = {
            "seq": len(self._events),
            "type": type,
            "timestamp": timestamp or _now_iso(),
            "actor": actor,
            "target": list(target),
            "payload": payload,
            "prev_hash": prev_hash,
        }
        h = compute_event_hash(event)
        event["event_id"] = f"evt-{h[:8]}"
        event["hash"] = h
        self._events.append(event)
        return event

    # ------------------------------------------------------------- 读取
    @property
    def events(self) -> list[dict]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self):
        return iter(self._events)

    def get(self, event_id: str) -> dict | None:
        for ev in self._events:
            if ev["event_id"] == event_id:
                return ev
        return None

    def by_type(self, type: str) -> list[dict]:
        return [ev for ev in self._events if ev["type"] == type]

    def upto(self, seq: int) -> list[dict]:
        return [ev for ev in self._events if ev["seq"] <= seq]

    # ------------------------------------------------------------- 完整性
    def verify_chain(self) -> bool:
        """校验 seq 连续、哈希自洽、链条衔接；失败抛 ChainBroken。"""
        prev = GENESIS
        for i, ev in enumerate(self._events):
            if ev.get("seq") != i:
                raise ChainBroken(f"seq 不连续: 期望 {i}, 实际 {ev.get('seq')}")
            if ev.get("prev_hash") != prev:
                raise ChainBroken(f"seq={i} prev_hash 断裂")
            expected = compute_event_hash(ev)
            if ev.get("hash") != expected:
                raise ChainBroken(f"seq={i} 内容哈希不匹配（历史被修改？）")
            prev = ev["hash"]
        return True

    def chain_head(self) -> str:
        return self._events[-1]["hash"] if self._events else GENESIS

    # ------------------------------------------------------------- 持久化
    def save_jsonl(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for ev in self._events:
                f.write(canonical(ev) + "\n")

    @classmethod
    def load_jsonl(cls, path: str | Path, *, verify: bool = True) -> "EventLog":
        events = []
        with Path(path).open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return cls(events, verify=verify)
