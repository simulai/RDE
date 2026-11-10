# 可证伪标准（Falsification Criteria）

文档版本：v0.1 ｜ 用途：为 RDE 自身的主张定义"什么算失败"。**没有可证伪条件的主张不得进入结论章节。**

## 1. 原则

依据理论边界第 3、6 条：逻辑一致、可复现都不等于正确。因此本仓库区分：

- **工程可证伪**（由测试判定）：实现是否符合规格；
- **理论可证伪**（由研究情形判定）：规格是否足以表达真实研究（需要真实案例，不由 pytest 判定）。

## 2. 可证伪条件登记

| ID | 主张 | 失败判据 | 判定方式 |
|----|------|---------|---------|
| F-R1.1 | 三状态维度足以表达 R1 六类命题 | 存在真实情形需违反任一转换表才能正确表达 | 理论（真实案例审查） |
| F-R1.2 | 证据不授予语义状态 | 任何路径出现"实验结果 → 定理"自动升级 | 工程（test_state_transitions） |
| F-R2.1 | 证明路线独立性判定正确 | 两条共享被推翻前提的路线被报为 still_valid | 工程构造 + 理论审查 |
| F-R2.2 | 影响传播完整 | 存在下游节点未进入影响报告 | 工程（test_dependency_propagation） |
| F-R3.1 | 不坍缩为单一评分 | 实现出现加权求和标量排序 | 代码审查（grep） |
| F-R3.2 | 决策可审计 | 决策记录缺"预期 vs 实际"回填 | 工程（schema 校验测试） |
| F-R4.1 | 可质疑自身策略 | 图中无法表示指向自身决策的质疑路径 | 工程 |
| F-R4.2 | 策略修订需外部/人类触发 | 仅凭系统自我评分即修订策略 | 工程 + 流程审查 |
| F-ES-01 | 同一日志重建同一状态 | `state_digest()` 不一致 | 工程（test_events） |
| F-ES-02 | 历史不可静默覆盖 | 存在修改旧事件而不产生断链告警的路径 | 工程（哈希链测试） |
| F-ES-03 | 定义修改不改变旧版本 | `state_at(旧seq)` 与初建时摘要不一致 | 工程（test_versioning） |
| F-DEP-01 | 冲突证据不被覆盖 | `mixed` 在无 invalidation 事件时变回 `supported` | 工程（test_events/test_state_transitions） |
| F-BND-01 | 九条理论边界无违反表述 | 文档出现被禁止的断言模式 | 文档审查（半自动 grep 清单） |

## 3. 第一阶段验收标准 → 测试映射

| # | 验收标准（任务书 §11） | 对应测试 |
|---|----------------------|---------|
| 1 | 同一事件日志重建同一知识状态 | `test_events.py::test_replay_consistency` |
| 2 | 修改定义不静默改变旧版本 | `test_versioning.py::test_definition_change_preserves_old_version` |
| 3 | 一个证据支持/反驳多命题 | `test_graph.py::test_one_evidence_multiple_claims` |
| 4 | 一个命题多条独立推导路径 | `test_graph.py::test_multiple_derivation_routes` |
| 5 | 单路线失败不自动推翻 | `test_dependency_propagation.py::test_single_route_failure_keeps_claim` |
| 6 | 冲突证据不被覆盖 | `test_state_transitions.py::test_conflicting_evidence_not_overwritten` |
| 7 | 基础变化触发下游审查 | `test_dependency_propagation.py::test_downstream_impact_report` |
| 8 | 决策可回溯 | `test_events.py::test_decision_traceability` |
| 9 | 数学/经验双验收路径 | `test_state_transitions.py::test_cross_track_upgrade_rejected` |
| 10 | 报告无法判断的事项 | `test_dependency_propagation.py::test_unjudgeable_reported` |

## 4. 升级规则

`HYPOTHESIS → 更高等级` 需要：外部证据或人类签署 + `human_approval_granted` 事件（见 epistemic_status.md §2.5）。系统内部的自我评价**不构成**升级依据（边界 8）。
