"""三状态维度转换表与合法性检查（Task 3，docs/state_semantics.md）。

设计要点：
1. 三个维度各自独立转换表，禁止单一状态字段（任务书 §4）。
2. 跨维度只有三条允许的联动（L1/L2/L3），本质是转换前置条件。
3. 证据状态只能由证据类事件驱动（原则 2/3）。
4. 命题语义状态的 true/false 转换必须绑定假设与适用范围（原则 4）。
5. 经验轨（empirical）永不授予语义状态（边界 4/5、可证伪条件 F-R1.2）。

所有表都是 DESIGN-DECISION；unknown/underdetermined 边界为 H-ST-001（开放问题 Q-ST-001）。
"""

from __future__ import annotations

from ..errors import IllegalTransition

# ---------------------------------------------------------------- 命题语义状态

PROPOSITION_TRANSITIONS: dict[str, frozenset[str]] = {
    "unknown": frozenset({"true_in_scope", "false_in_scope", "underdetermined", "not_applicable"}),
    "underdetermined": frozenset({"unknown", "true_in_scope", "false_in_scope"}),
    "true_in_scope": frozenset({"false_in_scope", "unknown", "not_applicable"}),
    "false_in_scope": frozenset({"true_in_scope", "unknown", "not_applicable"}),
    "not_applicable": frozenset({"unknown"}),
}

#: 允许驱动命题语义状态转换的 justification 路线。
#: empirical（经验轨）被显式排除 —— 证据不授予语义状态（理论边界 4/5）。
SEMANTIC_ROUTES = frozenset({"mathematical", "refutation", "scope_change", "reopening"})

TRUTH_VALUES = frozenset({"true_in_scope", "false_in_scope"})

# ---------------------------------------------------------------- 证据状态

EVIDENCE_TRANSITIONS: dict[str, frozenset[str]] = {
    "none": frozenset({"supported", "contradicted", "insufficient"}),
    "supported": frozenset({"mixed", "contradicted", "insufficient", "invalidated"}),
    "contradicted": frozenset({"mixed", "supported", "insufficient", "invalidated"}),
    "mixed": frozenset({"supported", "contradicted", "insufficient", "invalidated"}),
    "insufficient": frozenset({"supported", "contradicted", "mixed", "invalidated"}),
    "invalidated": frozenset({"none", "supported", "contradicted", "insufficient"}),
}

#: 只有这些事件类型可以驱动证据状态变化（原则 2/3 的执行点）。
EVIDENCE_DRIVERS = frozenset({"evidence_appended", "evidence_invalidated", "evidence_withdrawn"})

# ---------------------------------------------------------------- 工作状态

WORK_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"formalized", "archived"}),
    "formalized": frozenset({"active", "blocked", "superseded", "archived"}),
    "active": frozenset({"blocked", "completed", "superseded", "archived"}),
    "blocked": frozenset({"active", "archived"}),
    "completed": frozenset({"superseded", "archived", "active"}),
    "superseded": frozenset({"proposed", "active"}),
    "archived": frozenset({"proposed"}),
}

#: 这些转换必须携带显式 reopen 标记（M6 Reopen；原则 8/9 相关）。
REOPEN_REQUIRED = frozenset({
    ("archived", "proposed"),
    ("completed", "active"),
    ("superseded", "active"),
    ("superseded", "proposed"),
})


def _check_known(table: dict[str, frozenset[str]], value: str, dimension: str) -> None:
    if value not in table:
        raise IllegalTransition(f"未知{dimension}状态: {value!r}（可能是跨维度写入）")


def check_proposition_transition(
    from_state: str,
    to_state: str,
    *,
    justification: dict | None = None,
    scope: str | None = None,
) -> None:
    """校验命题语义状态转换。

    - from == to → 非法（no-op 不产生事件）
    - 不在转换表 → 非法（含跨维度写入，如 "proposed" → "true_in_scope"）
    - 转换到 true_in_scope/false_in_scope：必须有 justification.route ∈ SEMANTIC_ROUTES、
      非空 assumptions 绑定、非空 scope（原则 4）—— 即 L1 前置条件的结构化检查。
    """
    _check_known(PROPOSITION_TRANSITIONS, from_state, "命题")
    _check_known(PROPOSITION_TRANSITIONS, to_state, "命题")
    if from_state == to_state:
        raise IllegalTransition(f"命题状态 no-op: {from_state} → {to_state} 不产生事件")
    if to_state not in PROPOSITION_TRANSITIONS[from_state]:
        raise IllegalTransition(f"非法命题状态转换: {from_state} → {to_state}")

    if justification is None:
        raise IllegalTransition(f"命题状态转换 {from_state} → {to_state} 缺少 justification")
    route = justification.get("route")
    if route not in SEMANTIC_ROUTES:
        raise IllegalTransition(
            f"路线 {route!r} 不得驱动命题语义状态转换"
            "（经验轨不授予语义状态；可证伪条件 F-R1.2）"
        )
    if to_state in TRUTH_VALUES:
        assumptions = justification.get("assumptions") or []
        if not assumptions:
            raise IllegalTransition(
                f"{to_state} 必须绑定假设集合（原则 4）"
            )
        if not scope:
            raise IllegalTransition(f"{to_state} 必须绑定适用范围 scope（原则 4）")


def check_evidence_transition(from_state: str, to_state: str, *, driven_by: list | tuple | None = None) -> None:
    """校验证据状态转换：只能由证据类事件驱动（原则 2/3）。"""
    _check_known(EVIDENCE_TRANSITIONS, from_state, "证据")
    _check_known(EVIDENCE_TRANSITIONS, to_state, "证据")
    if from_state == to_state:
        raise IllegalTransition(f"证据状态 no-op: {from_state} → {to_state} 不产生事件")
    if to_state not in EVIDENCE_TRANSITIONS[from_state]:
        raise IllegalTransition(f"非法证据状态转换: {from_state} → {to_state}（冲突证据不得被覆盖）")
    if not driven_by:
        raise IllegalTransition(
            f"证据状态转换 {from_state} → {to_state} 缺少 driven_by（只能由证据类事件驱动）"
        )
    bad = [d for d in driven_by if d not in EVIDENCE_DRIVERS]
    if bad:
        raise IllegalTransition(
            f"事件类型 {bad} 不是证据类事件，不得驱动证据状态（逻辑/证据分离）"
        )


def check_work_transition(from_state: str, to_state: str, *, reopen: bool = False) -> None:
    """校验工作状态转换；终态重开必须显式 reopen（M6）。"""
    _check_known(WORK_TRANSITIONS, from_state, "工作")
    _check_known(WORK_TRANSITIONS, to_state, "工作")
    if from_state == to_state:
        raise IllegalTransition(f"工作状态 no-op: {from_state} → {to_state} 不产生事件")
    if to_state not in WORK_TRANSITIONS[from_state]:
        raise IllegalTransition(f"非法工作状态转换: {from_state} → {to_state}")
    if (from_state, to_state) in REOPEN_REQUIRED and not reopen:
        raise IllegalTransition(
            f"{from_state} → {to_state} 需要显式 reopen 事件（M6 Reopen，历史不被静默改写）"
        )


def transition_path_evidence(from_state: str, to_state: str) -> list[str] | None:
    """允许经 invalidated 中转的两步路径（如 supported → invalidated → contradicted）。

    返回实现该转换所需的中间状态列表（[] = 单步直接可达）；
    无可行路径返回 None。用于引擎在证据失效后合法地重算证据状态，
    保证『冲突证据不被单步覆盖』。
    """
    if from_state not in EVIDENCE_TRANSITIONS or to_state not in EVIDENCE_TRANSITIONS:
        return None
    if to_state in EVIDENCE_TRANSITIONS[from_state]:
        return []
    if (
        from_state != "invalidated"
        and "invalidated" in EVIDENCE_TRANSITIONS[from_state]
        and to_state in EVIDENCE_TRANSITIONS["invalidated"]
    ):
        return ["invalidated"]
    return None
