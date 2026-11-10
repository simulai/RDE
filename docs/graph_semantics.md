# 图语义（Graph Semantics）

文档版本：v0.1 ｜ 状态：`DESIGN-DECISION`（关系语义划分为人为约定，误分类风险见 design_risks.md R-003）

## 1. 节点（Node）

所有节点共享字段：`id`（稳定 ID）、`type`、`version`、`created_at`、`source`、`scope`（适用范围）。

| 类型 | 含义 |
|------|------|
| `Project` | 研究项目 |
| `Question` | 研究问题 |
| `Definition` | 定义 |
| `Assumption` | 假设 |
| `Claim` | 命题或研究主张 |
| `Derivation` | 推导或证明 |
| `Evidence` | 证据 |
| `Experiment` | 实验 |
| `Decision` | 研究决策 |
| `Artifact` | 代码、论文、数据、报告等产物 |
| `Version` | 对象版本（版本记录一等化） |
| `Event` | 研究状态变化事件（日志中的事件在读模型中的投影） |

ID 规则（M1）：`<TYPE小写>-<8位随机/递增slug>-<内容hash前6位>`，一经创建永不复用；内容修改产生**新版本**而非新 ID（分叉时产生新 ID 并以 `supersedes`/`fork_of` 连接）。

## 2. 边（Edge / Hyperedge）

每条边：`id`、`type`、`premises: [node_id…]`（可空，见方向）、`conclusions: [node_id…]`（≥1）、`created_at`、`source`、`scope`、`validity`。**允许 1..n 前提 → 1..n 结论**（超边）。

| 关系 | 类别 | 方向（premises → conclusions） | 严格语义 |
|------|------|-------------------------------|---------|
| `depends_on` | 逻辑/结构 | 依赖者 → 被依赖基础节点 | 结论节点的**形式成立条件**引用了前提节点 |
| `entails` | 逻辑 | 前提 → 结论 | 在绑定假设与适用范围内，前提（组）逻辑蕴含结论 |
| `supports` | 证据 | 证据 → 被支持命题 | 经验证据提高命题可信度；**绝不蕴含** `entails` |
| `contradicts` | 证据/冲突 | 证据或命题 → 冲突对象 | 与对象冲突；可指向命题或另一证据 |
| `tests` | 实验 | 实验 → 被检验命题 | 实验的判据针对该命题 |
| `instantiates` | 结构 | 一般 → 具体 | 具体对象是抽象对象的实例 |
| `refines` | 结构 | 粗 → 细 | 细化版本在重叠范围内更精确 |
| `supersedes` | 版本 | 新版本 → 旧版本 | 新版本取代；旧版本仍可回溯读取 |
| `motivates` | 研究管理 | 动机对象 → 被动机对象 | 研究动机；**不含**逻辑与证据含义 |
| `blocks` | 研究管理 | 阻塞原因 → 被阻塞对象 | 使对象不可执行；**不改变**其语义状态 |
| `derived_from` | 来源 | 结论/结果 → 来源 | 结果由来源产生（推导或数据处理） |

**禁止混用**（任务书第 3 节）：相关性、因果关系、逻辑蕴含、项目依赖是四类不同关系。当前 schema **不提供** `correlates_with` / `causes` —— 若需要，必须先在 graph_semantics 中定义独立语义再进 schema（待决 Q-EDGE-001：因果边是否属于 RDE 范围）。

## 3. 类别分离（原则 2 的结构化保证）

边分三个互斥类别：**逻辑类**（`depends_on`/`entails`）、**证据类**（`supports`/`contradicts`/`tests`）、**管理类**（`motivates`/`blocks`/`derived_from` 及结构类 `instantiates`/`refines`/`supersedes`）。

- 一条边只能有一个类别；schema 层不允许"又支持又蕴含"的边（需拆两条）。
- 状态机规则：证据类边只能影响**证据状态**；逻辑类边的成立只能由 `Derivation` 完成来确认（见 state_semantics.md 联动规则）。

## 4. 超边语义示例

```
entails:  premises=[A1(假设), D1(定义), C1(命题)]
          conclusions=[C2(命题)]
```
表示：在 A1、D1 成立且 C1 的语义状态为 `true_in_scope`（绑定 scope）时，C2 成立。该蕴含的**证明路线**由 `Derivation` 节点承载，`derived_from` 连接到上述前提。

## 5. 边的版本与失效

边同样有版本：前提节点版本变化时，旧边不删除，其 `validity` 置为 `superseded` 并由新版本事件覆盖（历史不静默覆盖——旧边始终可读，见 event_sourcing.md）。

## 6. 一个证据支持多命题；一个命题多路线

- 一个 `Evidence` → 多条 `supports`/`contradicts` 超边（验收标准 3）。
- 一个 `Claim` ← 多个 `Derivation`（验收标准 4）；路线独立性判定见 dependency_propagation.md（**开放问题 Q-DEP-001**）。
