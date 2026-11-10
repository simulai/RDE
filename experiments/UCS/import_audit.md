# UCS 真实研究数据导入审计（draft-import，待人工确认）

- 导入时间：2026-11-10；分支 `audit/phase1-1`；性质：**数据导入草案**（不是研究结论）
- 数据文件：
  - `experiments/UCS/definitions.json` — 8 条件定义节点（`definition-ucs-n1..n8`）
  - `experiments/UCS/hypotheses.json` — 28 个关系假设槽位（`claim-ucs-rel-XX-YY`，Hypothesis 节点形态）
  - `examples/ucs_research_graph.json` — 合并后可载入图（36 节点 / **0 条边**）
- 完整性测试：`tests/adversarial/test_ucs_import_integrity.py`（U01–U07）

## 1. 导入了什么

| 来源 | 内容 | 处置 |
|---|---|---|
| 任务书 §7 Test A | 八条件**名称**：N1 选择性信息压缩、N2 稳定离散化、N3 可组合结构、N4 后果接地、N5 双向耦合、N6 可修订性、N7 历史连续性、N8 有限资源协调 | 逐字进入 `content`（仅名称，不含解释） |
| 任务书 §7 Test A | 关系类型候选清单：必要 / 充分 / 互斥 / 替代 / 联合 | 作为**待选类型清单**写入 `_meta.relation_kinds_pending`，不是已确认分类 |
| 任务书 §7 Test A | 局部布尔组合空间 2^8 = 256 | 作为**封闭结构空间**计数写入 `_meta`（`combination_space: "closed"`），不枚举、不判定 |

## 2. 刻意未导入 / 未填写（不代填真相）

1. 每条条件的**完整语义与形式化定义** → `content` 内仅 `【待人工确认：完整定义与形式化】` 标记；
2. 任意两条条件之间的**关系类型、方向、真值** → 28 个槽位全部 `relation=null, direction=null, asserted=false, status=待人工确认`；
3. **单调性**：不预设任何单调关系（`monotonicity_assumed` 全为 `false`）；
4. 任何**证据、推导路线、组合判定结果** → `current_evidence=[]`、`routes=[]`、`proof_obligations` 全部 `status=open`；
5. 256 组合空间中的**任何具体组合** → 不枚举、不赋值。

## 3. 状态策略（全量核查见 U01–U03）

- 全部 36 节点：`proposition_state=unknown`、`evidence_state=none`、`work_state=proposed`；
- 图中 **0 条 `entails` 边**（`edges: []` 是刻意的：未确认的关系不进入图结构）；
- 关系假设以 **Hypothesis 节点**（claim 型槽位 + `hypothesis_slot` 元数据）登记，**不以 `entails` 边表达**。

## 4. 表示决策（需研究者确认）

| 决策 | 现状 | 待确认点 |
|---|---|---|
| 假设节点类型 | schema 节点类型枚举无 `hypothesis`；以 `claim` 型承载并附 `hypothesis_slot` 元数据 | 是否在 schema 新增独立 `hypothesis` 类型（属 schema/设计变更，本轮不擅自改） |
| 槽位枚举 | 8 条件两两配对 = 28 对**结构枚举**（与 256 组合空间同性质：登记*待研究空间*，非关系断言） | 确认是否需要全部 28 对，或按研究问题裁剪 |
| `examples/ucs_example.json` | Phase 1 占位文件（`definition-ucs-c1..c8` 短前缀，**不合 ID schema**） | 后续以本导入替换或标注废弃；本轮不删旧记录 |

## 5. 校验记录

- JSON Schema：8 定义 + 28 假设槽位全部通过 `node/claim.schema.json`（Draft 2020-12）；
- 引擎校验：逐节点 `validate_node` 通过（含 L1/L3 创建入口检查——全部 `unknown/proposed`，无绕过）；
- 引擎载入：36 节点经 `RDE.create_node` 全部创建成功，载入后状态仍为 `unknown/none/proposed`；
- 对抗完整性测试：`tests/adversarial/test_ucs_import_integrity.py` 全绿（见第 6 节）。

## 6. 待人工确认清单（不隐藏）

1. 八条件的完整定义与形式化（definitions.json 逐节点标记）；
2. 28 个关系假设槽位的关系类型/方向/依据（hypotheses.json 逐槽位标记）；
3. 是否新增 `hypothesis` 节点类型（第 4 节）；
4. 五类关系约束中哪些实际存在于 UCS 材料（当前仅为待选清单）；
5. Phase 1 占位文件 `examples/ucs_example.json` 的替换/废弃决定；
6. 真实 UCS 研究材料（论文/笔记/数据）的导入位置与引用方式（`source.ref` 目前只指向任务书）。
