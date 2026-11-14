# RDE — Research Dynamics Engine

**AGI 持续认知与知识演化机制研究**

- 项目阶段：理论建模与最小原型设计（第一阶段：最小可行研究内核）
- 文档版本：v0.1（对应《项目启动任务书 v0.1》）
- 状态：**研究假说与架构探索，非已证明理论**

---

## 1. 这是什么

RDE 是一个用于管理**研究知识状态**的内核：它追踪研究问题、命题、假设、定义、推导、证据、实验与研究决策，并在基础定义/假设/证据发生变化时，计算下游受影响的对象、检查证明路线、记录不可变事件日志。

它的长期研究目标是（**待验证的架构假说，不是已证明结论**）：

> 构建能够管理自身知识状态、持续形成和修订信念、根据证据调整研究方向，并保持长期认知连续性的机制。

核心研究问题：

> 一个有限智能系统，如何从持续产生的新信息中，形成稳定但可修订的信念和知识，并保持跨时间的认知连续性？

基本循环：

```
候选生成 → 约束 → 推导 → 验证 → 结晶 → 后果反馈 → 知识修订 → 新的研究策略
```

RDE **不是**：自动科研工具、多 Agent 任务调度器、已证明的 AGI 理论、或任何实验结论的来源。

---

## 2. 理论边界（必须随仓库传播）

以下边界按任务书第 8 节原文维护，任何文档、代码注释与对外表述都不得违反：

1. RDE 目前是研究假说和架构探索，不是已经证明的 AGI 理论。
2. 研究知识图谱不等于智能本身。
3. 逻辑一致性不等于现实正确性。
4. 形式化证明不等于经验真实性。
5. 证据支持不等于数学证明。
6. 研究过程可复现不等于研究结论正确。
7. 多 Agent 协作不自动产生集体智能。
8. 研究策略的自我评价不能替代外部验证。
9. 显式图结构未必是唯一实现方式，隐式动力学也可能实现相同功能。

完整讨论见 [`docs/theoretical_foundations.md`](docs/theoretical_foundations.md)。

---

## 3. 核心设计原则

1. 正确性优先于效率。
2. 逻辑关系与证据关系严格分离。
3. 数学证明与经验验证严格分离。
4. 任何结论都必须绑定定义、假设和适用范围。
5. 反例必须能够改变知识状态，而不只是被记录。
6. 定义、结论、证据和决策均需要版本管理。
7. 修改基础节点时，必须检查所有下游依赖。
8. 历史记录不可被静默覆盖。
9. 研究目标的重大修改必须经过人类授权。
10. 不允许 Agent 用自我生成的评价替代外部验证。

---

## 4. 四项核心研究问题（概要）

| 编号 | 名称 | 一句话 |
|------|------|--------|
| R1 | 知识状态管理 | True/False/Unknown 三值不够；需分离命题语义状态、认识与证据状态、项目执行状态 |
| R2 | 逻辑依赖与影响传播 | 基础节点被修改/推翻时，哪些下游受影响、哪些仍有效 |
| R3 | 有限预算下的研究策略选择 | 如何在不坍缩为单一评分的前提下选择下一步 |
| R4 | 研究策略自身的修订 | 系统必须能质疑自己的问题定义、假设、判据与评价标准 |

详见 [`docs/research_questions.md`](docs/research_questions.md)。

---

## 5. 架构概览

- **数据模型**：类型化、版本化、事件溯源的研究知识超图（Typed Versioned Event-Sourced Research Hypergraph）。支持多前提汇合、多结论共享证据、多条并行证明路线；不限制为树。
- **三状态维度**（禁止单一状态字段）：命题状态、证据状态、工作状态，各自独立的合法转换表。
- **事件溯源**：所有研究操作产生不可变事件；当前知识状态由事件日志重放重建；禁止覆盖历史。
- **依赖影响分析**：基础节点变化 → 下游可达集 → 按「证明路线」聚合判定结论是否仍被支撑（单条路线失效不自动推翻结论）。

详见 [`docs/architecture.md`](docs/architecture.md)、[`docs/graph_semantics.md`](docs/graph_semantics.md)、[`docs/state_semantics.md`](docs/state_semantics.md)、[`docs/event_sourcing.md`](docs/event_sourcing.md)、[`docs/dependency_propagation.md`](docs/dependency_propagation.md)。

---

## 6. 仓库结构

```
RDE/
├── README.md / LICENSE / CONTRIBUTING.md / ROADMAP.md
├── docs/            愿景、研究问题、理论边界、架构、状态语义、事件溯源、依赖传播、可证伪性、技术选型、风险登记、能力清单、消融研究、审查分级
├── schemas/         node / edge / event / claim / evidence 的 JSON Schema + 示例
├── core/            最小原型：graph、versioning、events、state_machine、dependency_analysis
├── experiments/     Test A: UCS / Test B: W3 / Test C: TRVC（结构占位，不含未获批准的结论）
├── research_log/    decisions / hypotheses / counterexamples / audits
├── reports/         阶段报告：基线、对抗审计、设计↔实现一致性、最终判定
├── tests/           自动化测试（含 tests/adversarial/ 反例审计套件）
└── examples/        事件日志与图的示例数据（重建演示）
```

---

## 7. 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install pytest jsonschema
.venv/bin/pytest tests/ -q        # 运行全部测试
.venv/bin/python examples/replay_demo.py   # 从事件日志重建同一知识状态
```

原型无外部服务依赖（纯 Python 标准库 + pytest/jsonschema 仅用于测试与校验）。技术选型比较见 [`docs/technology_comparison.md`](docs/technology_comparison.md)——第一阶段选型是**待验证的工程判断（H-TECH-001）**，不是既定前提。

---

## 8. 第一阶段验收标准

第一阶段完成不以代码行数、Agent 数量或界面效果为标准，而以任务书第 11 节的十项为准（同一日志重建同一状态、定义修改不静默改变旧版本、一个证据可支持/反驳多命题、多条独立推导、单路线失败不自动推翻、冲突证据不被覆盖、基础变化触发下游审查、决策可回溯、数学与经验双验收路径、系统能明确报告自己无法判断的事项）。对应测试见 `tests/`。

---

## 9. 明确禁止（第一阶段）

不开发大规模多 Agent 协作、自动论文生成、自动文献搜索；不接入昂贵大模型 API 作为核心依赖；不宣称 RDE 已解决 AGI 知识连续性问题；不把研究状态压缩成单一评分；不把各项目结论强行统一成一个理论；不擅自修改项目北极星或已有实验结论。

---

## 10. 实验项目状态

| 测试 | 目标 | 状态声明 |
|------|------|----------|
| Test A: UCS 八条件 | 多条件组合、分支、逻辑约束、反例管理（2^8=256 局部布尔组合空间） | **草案导入已就位**（`experiments/UCS/`：definitions / hypotheses / import_audit，全部标记待人工确认）；条件间不预设单调关系，关系假设以节点登记、无 entails 边 |
| Test B: W3 不可达路由 | 研究策略调度、意图修订、失败路线与负臂/作弊臂审计 | **草稿，尚未获正式 pilot 批准；本仓库不含任何虚构实验结果** |
| Test C: TRVC | 知识版本、例外学习、旧知识污染管理 | 待导入已有真实实验记录；不得重新解释或篡改实验结论 |

---

## 11. 许可与贡献

见 [`LICENSE`](LICENSE)、[`CONTRIBUTING.md`](CONTRIBUTING.md)。所有尚未证明的设计判断在文档中均以 **假说（H-xxx）/ 待决（Q-xxx）** 标记，登记于 [`docs/design_risks.md`](docs/design_risks.md)。

**RDE 本身也必须接受 RDE 的审计。**
