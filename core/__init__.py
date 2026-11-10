"""RDE 核心包 — Research Dynamics Engine 最小研究内核。

第一阶段（最小可行研究内核）实现：
- events: append-only 事件日志（唯一真相源）+ 确定性重放
- graph: 类型化超边读模型
- versioning: 不可变版本与分叉
- state_machine: 三状态维度合法/非法转换
- dependency_analysis: 下游影响传播与证明路线聚合
- engine: 把以上组装为统一入口（所有写操作先过状态机、再写事件、再更新读模型）

注意（docs/epistemic_status.md）：本包的测试通过只证明实现符合规格，不证明规格为真。
"""

from .errors import RDEError, IllegalTransition, ChainBroken, ReplayError, DependencyError
from .state_machine import (
    PROPOSITION_TRANSITIONS,
    EVIDENCE_TRANSITIONS,
    WORK_TRANSITIONS,
    check_proposition_transition,
    check_evidence_transition,
    check_work_transition,
)
from .events import EventLog, GENESIS, compute_event_hash
from .events.replay import replay, apply, state_digest, empty_state, ReplayError as _ReplayError
from .graph import ResearchGraph, downstream_of
from .versioning import bump_version, fork_node, assert_no_silent_overwrite
from .dependency_analysis import propagate, impact_report
from .engine import RDE

__all__ = [
    "RDEError", "IllegalTransition", "ChainBroken", "ReplayError", "DependencyError",
    "PROPOSITION_TRANSITIONS", "EVIDENCE_TRANSITIONS", "WORK_TRANSITIONS",
    "check_proposition_transition", "check_evidence_transition", "check_work_transition",
    "EventLog", "GENESIS", "compute_event_hash",
    "replay", "apply", "state_digest", "empty_state",
    "ResearchGraph", "downstream_of",
    "bump_version", "fork_node", "assert_no_silent_overwrite",
    "propagate", "impact_report",
    "RDE",
]
