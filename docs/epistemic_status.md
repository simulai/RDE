# 认识论状态说明（Epistemic Status）

文档版本：v0.1 ｜ 用途：给仓库中每一类陈述标注"这话有多可信"，防止研究假说被读成既定结论。

## 1. 状态等级

| 标签 | 含义 | 允许的使用场景 |
|------|------|----------------|
| `ESTABLISHED-IN-CODE` | 由自动化测试验证的工程事实 | "pytest X 通过"（必须附测试名） |
| `DESIGN-DECISION` | 已做出但可修订的工程决定 | 第一阶段数据模型字段选择 |
| `HYPOTHESIS (H-xxx)` | 待验证的理论/架构假说 | 愿景、R1–R4 可行性、技术选型推荐 |
| `OPEN-QUESTION (Q-xxx)` | 尚未裁决的问题 | design_risks.md 未解决问题清单 |
| `UNVERIFIED-CLAIM` | 有理由相信但无证据的表述 | 禁止进入结论章节 |
| `EXTERNAL-FACT` | 来自本仓库之外的事实 | 需附来源链接 |

## 2. 规则

1. **默认等级是 `OPEN-QUESTION`**。未标注的断言不被当作已证明结论。
2. 禁止将 `HYPOTHESIS` 改写为陈述句无标记版本（审查项：grep "证明"、"表明…必然"）。
3. 代码中的断言只有在有对应测试时才可标 `ESTABLISHED-IN-CODE`；测试只能验证**实现符合规格**，不能验证**规格为真**（边界 3、6）。
4. 三个测试项目（UCS/W3/TRVC）的任何结果均不得标为 `ESTABLISHED-IN-CODE`，除非：材料来源明确、人类授权导入、且 W3 已获 pilot 批准。
5. 外部验证 > 内部自评（边界 8）：`HYPOTHESIS` 升级为更高等级需外部证据或人类签署，事件日志中留下升级记录。

## 3. 本仓库当前主要假说索引

| ID | 假说 | 出处 | 状态 |
|----|------|------|------|
| H-VIS-001 | 存在可管理自身知识状态并保持认知连续性的机制 | docs/vision.md | 待验证 |
| H-TECH-001 | 纯 Python + JSONL 事件日志（+可选 SQLite）适合第一阶段 | docs/technology_comparison.md | 待验证（工程判断） |
| H-ARCH-001 | 类型化版本化事件溯源超图适合作为研究知识载体 | docs/architecture.md | 待验证 |
| H-DEP-001 | 按证明路线聚合的依赖传播不会误伤有效结论 | docs/dependency_propagation.md | 待验证（Q-DEP-001 独立性判定开放） |
| H-ST-001 | 三状态维度足以区分 R1 的六类命题情形 | docs/state_semantics.md | 待验证（F-R1.1 可证伪） |

（完整登记见 [design_risks.md](design_risks.md) §3（H-001 … H-009、H-TECH-001）；本表局部编号与其映射见 design_risks.md §5。凡标 *待并入* 的假说以本表为暂定登记，待回填主表。）

## 4. 与代码的对应

- 枚举与转换表 = `DESIGN-DECISION`；
- 测试通过 = 对应规格的 `ESTABLISHED-IN-CODE`；
- 算法文档中未被测试覆盖的段落 = `HYPOTHESIS`/`OPEN-QUESTION`。
