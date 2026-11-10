"""RDE 统一异常类型。"""


class RDEError(Exception):
    """RDE 所有受控错误的基类。"""


class IllegalTransition(RDEError):
    """非法状态转换（docs/state_semantics.md）。"""


class ChainBroken(RDEError):
    """事件哈希链被破坏：历史可能被静默修改（原则 8）。"""


class ReplayError(RDEError):
    """事件重放失败：未知事件类型、结构性矛盾或重放中违反状态机。"""


class DependencyError(RDEError):
    """依赖影响分析的输入错误。"""


class ValidationError(RDEError):
    """节点/边结构不符合最低约束。"""
