# 架构（Architecture）

文档版本：v0.1 ｜ 状态：`H-ARCH-001`（类型化版本化事件溯源超图适合作为研究知识载体）——**待验证假说**

## 1. 分层

```
┌────────────────────────────────────────────────────┐
│  L4  研究日志层   research_log/ (decisions/hypotheses/  │
│                   counterexamples/audits) 人类可读      │
├────────────────────────────────────────────────────┤
│  L3  分析层       dependency_analysis  影响传播、        │
│                   证明路线聚合、影响报告                 │
├────────────────────────────────────────────────────┤
│  L2  状态层       state_machine  三维度合法转换；        │
│                   versioning     不可变版本/分叉         │
├────────────────────────────────────────────────────┤
│  L1  存储层       events (append-only 事件日志)  ← 真相源 │
│                   graph  (由事件重放得到的读模型)         │
└────────────────────────────────────────────────────┘
```

**核心不变式**：L1 是唯一真相源（source of truth）。`graph` 是**读模型**，任何时刻可丢弃并由事件日志重放重建（验收标准 1）。对图的任何修改必须先转化为事件。

## 2. 模块职责与文件

| 模块 | 职责 | 关键约束 |
|------|------|---------|
| `core/events` | 事件定义、append-only 日志、重放 | 无更新/删除 API；事件含 `prev_hash` 形成哈希链 |
| `core/graph` | 节点/超边读模型、查询、类型化注册 | 支持多前提多结论的超边；不提供直接改写历史的接口 |
| `core/versioning` | 版本记录、`supersedes`、Fork Definition | 版本不可变；旧版本可回溯读取 |
| `core/state_machine` | 三状态维度转换表与合法性检查 | 非法转换抛 `IllegalTransition`；跨维度联动规则集中于此 |
| `core/dependency_analysis` | 下游可达、证明路线聚合、影响报告 | 单路线失效不推翻结论；输出必须含"仍有效集" |

依赖方向：`dependency_analysis → graph/events`；`graph → events`；`state_machine` 不依赖 `graph`（纯函数式转换表）。**禁止**反向依赖（如 `events` 调用 `dependency_analysis`），保证重放是确定性的纯重放。

## 3. 数据流（一次研究操作）

```
操作请求 (create_node / append_evidence / refute_assumption / …)
   → state_machine 合法性检查（不合法 → 拒绝，不写事件）
   → 构造 Event（含 actor、timestamp、payload、引用的定义/假设版本）
   → 事件追加（哈希链接）
   → 读模型更新（同一进程内同步 apply，保证读己之写）
   → 若为基础节点变化 → dependency_analysis 生成影响报告（报告本身也是一个事件/Artifact）
```

## 4. 超图而非树

全局科研关系需要支持（任务书第 3 节）：

- 多个前提汇合 → 一个结论（超边 `premises: [..] → conclusions: [..]`）；
- 一个证据共享给多个命题（同一 `Evidence` 节点多条 `supports` 超边）；
- 多条证明路线并行（同一 Claim 多个 `Derivation`）。

多叉树只在局部假设分支（M6 Branch/Fork）使用；`Branch/Merge/Prune/Reopen` 作为事件操作，不改变全局图结构类型。

## 5. 与 Agent 的边界

第一阶段**不做完整 Agent 系统**（任务书第 6 节）。架构上预留：所有事件含 `actor` 字段（`human`/`agent:<id>`/`system`），但：

- 原则 9：`north_star`/研究目标类事件的 `actor` 必须为 `human`（代码层校验，M 阶段扩展）；
- 原则 10：`actor=agent` 的自我评价事件不能触发语义状态升级，只能产生 `proposed` 状态转换，需外部/人类签署事件确认。

## 6. 第一阶段非目标（任务书第 12 节）

无多 Agent 协作、无自动论文生成、无文献搜索、无大模型 API 依赖、无统一评分、无统一理论、无北极星擅改。

## 7. 替代实现路径（边界 9）

显式图结构未必是唯一实现：关系数据库递归 CTE、文档+索引、甚至隐式动力学（无显式节点的对象系统）都可能实现相同功能。本架构的**可证伪点**在于：若第一阶段测试显示"必须在读模型中显式遍历才能完成影响分析"不成立（即存在更简实现满足全部十项验收标准），则 H-ARCH-001 需要修订。

**待决 Q-ARCH-001**：读模型与事件日志的 schema 演进如何兼容（事件升级策略未定，见 event_sourcing.md §6）。
