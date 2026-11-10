# ROADMAP

状态标记：`[done]` 第一阶段已交付 ｜ `[next]` 待做 ｜ 不含任何未获授权的承诺

## 第零阶段：项目启动（本次交付）

- [x] 仓库结构、README、愿景、研究问题、理论边界（Task 1）
- [x] 数据模型 JSON Schema + 示例数据（Task 2，schemas/、examples/）
- [x] 三状态维度语义与合法/非法转换（Task 3，docs/state_semantics.md + core/state_machine）
- [x] 事件溯源机制（Task 4，docs/event_sourcing.md + core/events）
- [x] 依赖传播算法，含多证明路线（Task 5，docs/dependency_propagation.md + core/dependency_analysis）
- [x] 最小原型（Task 6，core/：节点/关系/版本/事件/依赖分析/状态检查）
- [x] ≥10 自动化测试（Task 7，tests/）
- [x] 技术选型比较（docs/technology_comparison.md）
- [x] 《设计风险与未解决问题》（docs/design_risks.md）

## 第一阶段：最小可行研究内核（里程碑 M1–M7）

- [x] M1 研究对象标准化（节点类型/字段/ID 规则 → schemas/ + core/graph）
- [x] M2 研究知识图谱（节点、超边、依赖、版本引用）
- [x] M3 事件溯源（append-only 日志 + 重放）
- [x] M4 状态转换（合法转换检查，防非法升级）
- [x] M5 依赖影响分析（下游受影响对象计算 + 影响报告）
- [x] M6 研究分支管理（Branch/Merge/Prune/Reopen/Fork Definition —— 第一阶段为事件与 API 层实现，`fork` 语义见 examples 与测试）
- [x] M7 研究决策记录（Decision 字段：目标/选项/理由/预算/预期价值/实际结果/有效性）

第一阶段验收：以 docs/falsification_criteria.md §3 的十项映射为准，**不以代码行数、Agent 数量或界面效果为标准**。

## 第二阶段（候选，均待人类授权与风险评审后才启动）

> 以下全部为 `[next]`，受第 12 节禁令约束；启动条件 = design_risks.md 中 R-001…R-005 的高风险项有缓解方案。

- [ ] 导入 UCS 真实条件材料（结构性测试 → 真实数据，需来源确认）
- [ ] W3 pilot：**须先获正式 pilot 批准**，不得预写实验结果
- [ ] TRVC 真实实验记录导入（只读导入，不得重新解释结论）
- [ ] 事件 schema 版本化策略落地（Q-ARCH-001）
- [ ] 规模化：影响分析增量计算（Q-DEP-002）
- [ ] 可视化审计界面（只读重放查看器）

## 明确不在路线图上（任务书第 12 节禁令）

大规模多 Agent 协作、自动论文生成、自动文献搜索、昂贵大模型 API 核心依赖、统一评分、统一理论、北极星擅改。
