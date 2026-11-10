# RDE Phase 1.1 — 设计↔实现一致性对照表（T3）

对照基准：`docs/`（architecture / event_sourcing / state_semantics / dependency_propagation /
graph_semantics / falsification_criteria / design_risks / theoretical_foundations）与任务书承诺。
"测试"列给出可复跑的用例（Phase 1 原 42 项 + Phase 1.1 对抗 68 项）。
分类口径（任务指定五类）：**已实现且测试覆盖 / 已实现但未充分测试 / 仅文档设计 / 实现与文档冲突 / 设计尚未解决**。

## 0. 分类汇总

| 分类 | 条数 | 说明 |
|---|---|---|
| 已实现且测试覆盖 | 26 | 含 11 项 Phase 1.1 **修复后**转正的条目（原为冲突） |
| 已实现但未充分测试 | 4 | 实现存在，测试密度不足 |
| 仅文档设计 | 6 | 文档有承诺、代码无实现（多为第二阶段/待决项） |
| 实现与文档冲突 | 12 | 其中 **11 条已在本轮以最小修复拉回文档**（逐条披露），1 条（L1 路线存在性）开放 |
| 设计尚未解决 | 5 | 代码层不可单方面修复，需研究者裁决（Q-007 / R-017 / L1 边界等） |

## 1. 已实现且测试覆盖

| # | 设计承诺（文档/章节） | 实现位置 | 测试 | 备注 |
|---|---|---|---|---|
| 1 | 事件溯源：`KnowledgeState = fold(replay, initial, events)`；seq 为唯一顺序权威（event_sourcing §1/§4，验收 1） | `core/events/replay.py` | `test_events::test_replay_consistency`、`a02b`、`a07` 全组 | 对抗复核：换序重放同 digest |
| 2 | append-only + SHA-256 哈希链（event_sourcing §1，原则 8，验收 1） | `core/events/__init__.py` | `a01`/`a05`/`a08`/`a09`/`a11` | 裸 `replay()` 层例外见 §4 注（F-A01） |
| 3 | 未知事件类型拒绝、非法历史在重放层被拦截（event_sourcing §4；重放=第二重校验） | replay handlers + `state_machine` | `a06`/`a07`/`a07b`/`e04` | 攻击者重算哈希仍被语义层拦截 |
| 4 | 无删除/更新 API；事件与节点历史不可静默覆盖（原则 8） | `EventLog`/`RDE` | `f09`/`d08` | 任何 `delete_*` 均不存在 |
| 5 | 时间点回溯、旧版本不被静默改写（event_sourcing §5.1，验收 2） | `state_at`/`history` | `b01`/`b07`/`test_versioning` | 含旧 Derivation 逐字节不变 |
| 6 | Fork 双向隔离；失效边保留不删除（graph_semantics §5，原则 8） | `fork_node`/`edge_validity_changed` | `b04`/`b05`/`b06`/`f08` | |
| 7 | 三状态维度 + 转换表集中（state_semantics §1-3） | `core/state_machine` | phase1 11 项 + `a` 系列 | 非法转换抛 `IllegalTransition` |
| 8 | L1 的**结构绑定子条件**：真值必须绑定 assumptions + scope，且语义路线（非经验）驱动（state_semantics L1，原则 4） | `check_proposition_transition` | phase1 跨轨测试、`a07b`、`e02` | L1 完整定义的缺口见 §4 |
| 9 | L3 证明义务：Claim→completed 前义务须完成（state_semantics L3） | `set_work_state` + `validate_node` | `e05`/`e05b` + 修正后 phase1 用例 | **Phase 1.1 修复**（F-E03，已披露） |
| 10 | 经验轨不得授予语义状态（理论边界 4/5，F-R1.2） | `SEMANTIC_ROUTES` 白名单 | `test_cross_track_upgrade_rejected`、`a07b`、`d09` | 含证据状态驱动白名单 |
| 11 | 传播算法：下游可达 + 路线聚合 + 报告必含"仍有效集/无法判定集"（dependency_propagation §2-4，验收 4/7/10） | `core/dependency_analysis` | `c01`/`c04`、phase1 验收组 | |
| 12 | `still_valid ≠ 正确`：不改命题状态、不产生非提议语义事件、action 恒 `review_routes`（验收 5，原则 10） | `propagate` | `c06`/`c05` | 含"报告后无新增真值事件"断言 |
| 13 | H-DEP-002：状态离场只写 `proposed_only` 提议，执行需人类批准（dependency_propagation §5） | `engine.impact` | `c05`、phase1 | |
| 14 | 冲突证据不被覆盖，离开 mixed 必经 invalidated 中转（state_semantics §2，验收 6） | `_recompute_evidence_state` | `d01`-`d05`、phase1 | 事件序列显式断言 |
| 15 | 证据撤回 / 失效双通路，均带原因与 actor（state_semantics §2，event_sourcing §3） | `withdraw_evidence`/`invalidate_evidence` | `d02`/`d03` | **Phase 1.1 修复**（F-D01） |
| 16 | `sufficiency → insufficient` 通路（state_semantics §2 语义） | `_recompute_evidence_state` | `d06`/`d07` | **Phase 1.1 补入 schema**（F-D02） |
| 17 | 北极星第一阶段禁改：无 API + 重放拒绝 + schema actor 闸门（任务书 §12） | 三处独立闸门 | `e03` | 三闸门同时验证 |
| 18 | 人类授权必须 human actor（原则 9/10） | `approve` | `e08`、phase1 | agent 签发被拒 |
| 19 | 决策可回溯（M7，验收 8） | `record_decision`/`backfill_decision` | phase1 `test_decision_traceability` | |
| 20 | 边界 8：自我评价不替代外部验证（决策有效性） | `backfill_decision` 守卫 | `e06` | **Phase 1.1 修复**（F-E04） |
| 21 | 边类型/类别不混用（graph_semantics §3） | `validate_edge` + `edge.schema.json` | `f06`/`g04`（代码+schema 双闸门） | |
| 22 | ID 稳定前缀规则、引用存在性、空端点拒绝（graph_semantics §1-2） | `validate_node/edge` + schema | `f05`/`g05`/phase1 | |
| 23 | 超边多层传播、循环有界终止、失效边不参与遍历 | `implicit_downstream`/`propagate` | `f01`/`f02`/`f03`/`f08` | 环警告缺失见 §2 |
| 24 | 归档=剪枝而非删除（原则 8，prune 语义） | `set_work_state`/`prune_branch` | `f07`、phase1 | 归档前提 → 路线 broken |
| 25 | 失败的创建不得写入事件（事件溯源自洽性；**由本轮发现推导的不变式**） | 创建入口前置拒绝 | `f04` | **Phase 1.1 修复**（F-A03，Major） |
| 26 | 多节点影响报告的 schema 契约（event_sourcing §3） | `event.schema.json` | `g01`/`g01b`/`g02b`/`g02` | **Phase 1.1 修复**（F-G01） |

## 2. 已实现但未充分测试

| # | 设计承诺 | 实现位置 | 现有测试 | 缺口 |
|---|---|---|---|---|
| U1 | 循环依赖的处理（正确性优先，不得挂死） | `visited` 集合 | `f02`/`f03` | 仅验证终止；无"检测到环"的报告（F-F01，设计未承诺 → 观察项） |
| U2 | `merge_branch` 后的时间点回溯语义 | `state_at` + 分支事件 | phase1 仅覆盖 branch/prune | 合并/回滚与 `state_at` 的组合语义未测 |
| U3 | 影响报告在混合 Δ（modified+refuted 混合）下的逐条保真 | `propagate` | 单 kind 测试充分 | 多节点 `kind` 折叠为 modified（F-G02，Low） |
| U4 | 事件 payload 的 schema 契约 | 测试/CI 层执行（运行时不做 —— 文档未承诺运行时校验） | `g02`/`g02b`/phase1 schema 测试 | 覆盖面依赖样本与构造场景，无属性测试（随机事件序列） |

## 3. 仅文档设计

| # | 设计承诺（文档） | 现状 | 测试 |
|---|---|---|---|
| D1 | **L2**：proposed→formalized 前置条件 = 所有引用 Definition 版本已确定（state_semantics L2） | **未实现**（引用不存在定义也可 formalized） | `e10` 固化事实（非正确性证据） |
| D2 | HYPOTHESIS → 更高等级的升级规则，需外部证据/人类签署 + `human_approval_granted`（falsification §4、epistemic_status §2.5） | 无 `hypothesis` 节点类型、无升级 API | 无（第二阶段） |
| D3 | 反例自动落 `research_log/counterexamples/` 且不可删除（state_semantics §5.4） | 目录约定存在（仅 README 占位），无写入机制 | 无（依赖导入/落盘工具，第二阶段） |
| D4 | 事件 schema 演进策略 / `schema_version` 启用（event_sourcing §6，Q-ARCH-001） | 预留未启用，文档明标"待决" | 无 |
| D5 | 多 Agent 协作语义（理论边界 7；第二阶段） | 无 | 无 |
| D6 | 因果边 `causes` 是否属于 RDE（graph_semantics Q-EDGE-001，"待决"） | schema 不提供 | `f06` 反向确认未知类型被拒 |

## 4. 实现与文档冲突

> 前 11 条已在 Phase 1.1 以**最小修复**拉回文档承诺（详见 `reports/adversarial_audit.md` §9 修复清单），
> 每条都有修复前后证据；第 12 条开放。

| # | 文档承诺 | 冲突表现（修复前） | 处置 | 测试 |
|---|---|---|---|---|
| X1 | 原则 10/architecture §5：Agent 自评不得授予语义状态 | `actor="agent:*"` 可直接执行 `unknown→true_in_scope` | ✅ 修复：非 human 执行真值升级拒绝，仅 `proposed_only` | `e01` |
| X2 | L1（原则 4）在所有入口生效 | 创建入口可直接携带未绑定 `true_in_scope` | ✅ 修复：`validate_node` 强制 assumptions+scope | `e02`/`e02b` |
| X3 | L3：证明义务满足才能 completed | 义务 `open` 的 Claim 可完成；**Phase 1 既有测试反而断言了该违规路径** | ✅ 修复 + 既有测试按文档修正（重点披露） | `e05`/`e05b`、修正后 phase1 用例 |
| X4 | state_semantics L3 + 撤回语义有可达通路 | `evidence_withdrawn` 有事件/有 handler、无 API | ✅ 修复：`withdraw_evidence` | `d02` |
| X5 | 推导撤销即路线失效（state_semantics §5.2） | `invalidate_derivation` 后路线仍 `intact` | ✅ 修复：`_route_status` 检查路线自身 status | `c07`/`c08` |
| X6 | `sufficiency` 机制（实现存在）与 schema 契约一致 | 字段不在 `evidence.schema.json` | ✅ 修复：schema 增补枚举 | `d06`/`g03` |
| X7 | 影响报告必须可过 schema（Δ 为多元组，算法文档） | 多节点 `change.node` 数组被 schema 拒绝 | ✅ 修复：`oneOf[string, array]` | `g01` |
| X8 | 链校验是所有载入入口的职责（event_sourcing §1） | `RDE(EventLog(verify=False))` 不校验；`RDE(list)` 崩溃 | ✅ 修复：`__init__` 统一 `verify_chain` + list 支持 | `a08` |
| X9 | 事件溯源不允许覆盖（原则 8 的自洽性） | `_emit` 先写后应用：重复创建抛错时**日志已被毒化** | ✅ 修复：7 个创建入口前置拒绝 + 日志零污染不变式 | `f04` |
| X10 | 边界 8：自我评价不替代外部验证 | `agent` 可自评 `decision_effective=True` 无外部验证 | ✅ 修复：human 签署或 `external_validation_ref` | `e06` |
| X11 | 证据状态只能由证据事件驱动 + 证据撤回通路存在 | （撤回通路即 X4；驱动白名单本身一致） | ✅ 双闸门验证 | `d09`/`d02` |
| X12 | **L1 完整定义**：真值前置条件 = 存在 `completed` 的 Derivation 路线（state_semantics L1 原文） | 只实现了绑定子条件；**没有任何"completed 推导路线存在"检查**（与 refute 离场路径存在张力，见 §5-S3） | ⚠️ **未修复**：属语义裁决，不擅自实现 | `e09` 固化事实 |

## 5. 设计尚未解决（需研究者裁决，代码不可单方面修复）

| # | 条目（ID） | 问题 | 现状证据 | 建议裁决点 |
|---|---|---|---|---|
| S1 | **Q-007 / H-DEP-001**（隐藏前提） | 路线独立性 = 按声明的前提集；未声明的隐藏前提不可检测 | `c02a`（命题在报告中不可见）、`c02b`（`still_valid` 假阳性） | 是否引入"前提完备性审计"（人工勾稽/导入时强制）；兜底已存在（`review_routes` 强制复核、不授予正确性） |
| S2 | **R-017 / Q-007**（版本引用漂移） | premise 按 ID 解析到当前版本，路线无法钉住 v1 | `b03`（`definition_versions` 与路线解析漂移）、`c03`（"引用不同版本"不可区分） | 是否在 derivation premise 引入 `bound_versions`；修订当刻的影响报告是现有缓解 |
| S3 | **L1 边界**（state_semantics L1 vs §5 反例离场） | L1 要求 completed 推导路线；但反例离场（refute→false_in_scope）走 `refutation` 路线，若严格执行 L1 将封死原则 5 的离场路径 | `e09`（现状：无路线检查） | 裁决 L1 的精确边界：`true` 严格要求推导路线；`false` 是否允许反例路线单独成立 |
| S4 | **Q-EDGE-001**（因果边） | `causes` 是否属于 RDE 第一阶段范围 | schema 无该类型（`f06` 拒绝） | 范围裁决 |
| S5 | **R-014 / Q-011**（规模上限） | 超图规模、事件数、重放时延的上限未验证 | 无性能测试 | 第二阶段前定义压测基准（风险登记表要求） |

## 6. 验收标准 → 测试复核（任务书 §11，十条）

| # | 验收标准 | Phase 1 测试 | Phase 1.1 对抗复核 | 结论 |
|---|---|---|---|---|
| 1 | 同一日志重建同一状态 | `test_replay_consistency` | `a01-a11`（篡改/调序/删事件/未知/非法注入） | ✅ 成立（链+语义双层） |
| 2 | 修改定义不静默改变旧版本 | `test_definition_change_preserves_old_version` | `b01`/`b07`（旧证明逐字节不变 + 时间点回溯） | ✅ 成立（版本钉住缺口另记 S2） |
| 3 | 一个证据支持/反驳多命题 | `test_one_evidence_multiple_claims` | `d01`/`d04` | ✅ 成立 |
| 4 | 一个命题多条独立推导路径 | `test_multiple_derivation_routes` | `c01`（真独立双向）/`c03`（版本不可区分，S2） | ✅ 成立（独立性定义=按声明，S1） |
| 5 | 单路线失败不自动推翻 | `test_single_route_failure_keeps_claim` | `c06`（不授予正确性、无自动语义事件）/`c07`（撤销路线判失效） | ✅ 成立 |
| 6 | 冲突证据不被覆盖 | `test_conflicting_evidence_not_overwritten` | `d03`（必经 invalidated 中转序列）/`d05` | ✅ 成立 |
| 7 | 基础变化触发下游审查 | `test_downstream_impact_report` | `b02`（修订即报告）/`f01`（多层） | ✅ 成立 |
| 8 | 决策可回溯 | `test_decision_traceability` | `e06`（有效性回填受原则 10 约束） | ✅ 成立 |
| 9 | 数学/经验双验收路径 | `test_cross_track_upgrade_rejected` | `a07b`（伪造经验升级重放被拒）/`d09` | ✅ 成立 |
| 10 | 报告无法判断的事项 | `test_unjudgeable_reported` | `c04`（broken+unknown → unjudgeable 且理由完整） | ✅ 成立 |

> 十条验收标准在对抗复核后均成立；但按任务纪律，**验收成立 ≠ 设计已解决**：
> S1/S2/S3 是验收标准文字之外的开放设计问题，测试通过不能替代其裁决。
