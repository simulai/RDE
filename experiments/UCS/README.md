# Test A — UCS 八条件

- **目标**：检验多条件组合、分支、逻辑约束和反例管理（任务书 §7）。
- **规模事实**：八项条件；局部布尔组合空间 2^8 = 256（结构性事实，非实验结论）。
- **状态**：`structural-example` — 本仓库当前只有结构示例（`examples/ucs_example.json`），
  真实条件材料与条件间关系**待导入**。
- **约束**：
  - 支持 T/F/U 或更精细状态（三状态维度，见 docs/state_semantics.md）；
  - 记录条件间必要、充分、互斥、替代、联合约束；
  - **不预设条件之间存在单调关系**。
- 数据形状：`examples/ucs_example.json`（含 `_meta.warnings`，声明其占位性质）。
