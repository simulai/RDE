# 状态语义（State Semantics）— Task 3

文档版本：v0.1 ｜ 状态：`DESIGN-DECISION`，其中枚举边界（如 `underdetermined` vs `insufficient`）为 `H-ST-001`，**待验证**（可证伪条件 F-R1.1）

## 0. 原则

禁止单一状态字段表达一切。三个状态维度**相互独立存储、独立转换、有限联动**。代码中对应三个枚举与三张转换表（`core/state_machine`）。

---

## 1. 维度一：命题语义状态（PropositionState）

回答："在绑定的假设与适用范围内，命题本身成立吗？"

| 值 | 含义 | 绑定要求 |
|----|------|---------|
| `true_in_scope` | 在明确假设集与适用范围内为真 | 必须绑定 `assumptions`（版本引用）与 `scope` |
| `false_in_scope` | 在明确假设集与适用范围内为假 | 同上 |
| `unknown` | 尚未判定/尚在研究中 | 无绑定要求 |
| `underdetermined` | 已确认当前假设集/公设**结构性不足以**决定真值（含独立性问题、数据原则上不可区分） | 须绑定"为何欠定"的推导或判定记录 |
| `not_applicable` | 命题的适用范围与当前语境不相交 | 须绑定 scope 判定 |

**`unknown` vs `underdetermined`（开放问题 Q-ST-001）**：`unknown` = 还没有判定（过程性）；`underdetermined` = 已判定"给定框架下不可判定"（结构性）。二者边界是当前设计的模糊点（design_risks R-002/Q-002），暂以"是否存在'为何欠定'的判定记录"作为可操作区分。

### 1.1 合法转换表（PropositionState）

```
unknown            → true_in_scope | false_in_scope | underdetermined | not_applicable
underdetermined    → unknown | true_in_scope | false_in_scope        (前提/范围变化后重判)
true_in_scope      → false_in_scope | unknown | not_applicable
false_in_scope     → true_in_scope | unknown | not_applicable
not_applicable     → unknown                                        (范围重新纳入)
```
- 无自环转换（`X → X` 视为 no-op，不产生事件）。
- `true_in_scope ↔ false_in_scope` 必须携带 `justification`（推导事件或反例事件引用）。

### 1.2 非法转换（示例，测试覆盖）

| 非法转换 | 违反 |
|----------|------|
| `unknown → true_in_scope` **由证据事件触发** | 原则 2/3、边界 5（证据不授予语义状态） |
| `proposed → true_in_scope`（跳过 formalized/推导） | 原则 4（未绑定定义与假设） |
| `true_in_scope` 无 `assumptions`/`scope` 绑定 | 原则 4 |
| `supported → true_in_scope`（把证据状态写进语义状态） | 维度混淆 |
| 任何语义转换由 `actor=agent` 自我评价单独触发 | 原则 10 |

---

## 2. 维度二：证据状态（EvidenceState）

回答："我们当前掌握的外部证据对该对象说明了什么？"（对象：主要为 Claim，亦可为 Assumption/Definition 的经验性内容）

| 值 | 含义 |
|----|------|
| `none` | 尚无任何证据记录 |
| `supported` | 现有证据一致支持（无已知冲突） |
| `contradicted` | 现有证据一致反驳 |
| `mixed` | **存在冲突证据，双方均未被推翻**（冲突不被覆盖，验收标准 6） |
| `insufficient` | 有证据但不足以改变倾向/存在关键缺口 |
| `invalidated` | 用于判定的证据本身被撤回/失效，状态归零待重判 |

### 2.1 合法转换表（EvidenceState）

```
none          → supported | contradicted | insufficient
supported     → mixed | contradicted | insufficient | invalidated
contradicted  → mixed | supported  | insufficient | invalidated
mixed         → supported | contradicted | insufficient | invalidated
insufficient  → supported | contradicted | mixed | invalidated
invalidated   → none | supported | contradicted | insufficient   (重判后)
```
- `supported → contradicted` 只允许**新反驳证据压倒性且旧证据被 invalidation 事件撤回**的路径；否则必须经 `mixed`（防止"新证据覆盖旧冲突"，验收标准 6）。
- 证据状态**只能由证据类事件**（`evidence_appended`/`evidence_invalidated`/`evidence_withdrawn`）驱动。

### 2.2 非法转换

| 非法转换 | 违反 |
|----------|------|
| 由 `derivation_completed` 事件驱动的任何证据状态变化 | 逻辑/证据分离 |
| `mixed → supported` 通过**删除**冲突证据实现（删除 API 不存在） | 历史不可静默覆盖 |
| `none → supported` 直接写入（无证据事件） | 事件溯源 |

---

## 3. 维度三：工作状态（WorkState）

回答："该对象在研究流程中处于什么阶段？"

| 值 | 含义 |
|----|------|
| `proposed` | 已提出，未形式化 |
| `formalized` | 已形式化（定义/符号/义务绑定完成） |
| `active` | 正在研究/检验 |
| `blocked` | 被依赖或外部条件阻塞（`blocks` 边） |
| `completed` | 完成（对 Claim：证明义务或验证义务已按对应轨道满足） |
| `superseded` | 已被新版本取代（仍可回溯读取） |
| `archived` | 归档（默认终态，需显式 reopen） |

### 3.1 合法转换表（WorkState）

```
proposed     → formalized | archived
formalized   → active | blocked | superseded | archived
active       → blocked | completed | superseded | archived
blocked      → active | archived                  (解除阻塞必须先回 active)
completed    → superseded | archived | active     (active 仅经 reopen 事件)
superseded   → proposed | active                  (reopen/reopen-question)
archived     → proposed                           (仅经 reopen 事件)
```

### 3.2 非法转换

| 非法转换 | 违反 |
|----------|------|
| `proposed → completed` | 跳过形式化与检验 |
| `blocked → completed` | 未解除阻塞不得完成 |
| `archived → active`（无 reopen 事件） | M6 Reopen 必须显式 |
| `formalized → true_in_scope`（跨维度写入） | 维度混淆 |

---

## 4. 跨维度联动规则（仅有的三条允许联动）

联动**不是**维度混合，而是"转换前置条件"：

| 规则 | 内容 |
|------|------|
| L1 | `PropositionState → true_in_scope / false_in_scope` 的前置条件：存在一条 `completed` 的 `Derivation` 路线，其 `derived_from` 前提当前有效，且事件携带 `assumptions`+`scope` 绑定。 |
| L2 | `WorkState: proposed → formalized` 的前置条件：所有引用的 `Definition` 版本已确定（版本事件存在）。 |
| L3 | `WorkState → completed`（对 Claim）的前置条件：证明义务已满足（数学轨：L1 的推导）**或**验证义务按经验轨满足并有人类/外部签署的 `Decision` 事件。两轨不得互授（理论边界 §3）。 |

**非法联动**（反例，测试覆盖）：`EvidenceState: none → supported` 后直接产生 `PropositionState: unknown → true_in_scope`——系统必须拒绝，除非同时存在满足 L1 的推导。

---

## 5. 反例改变知识状态（原则 5）

反例不是"被记录下来"就结束：

1. 反例证据事件 → 触发 `EvidenceState` 向 `contradicted`/`mixed` 转换；
2. 若反例命中某条 `Derivation` 的前提 → 该路线标为 `invalidated`，触发依赖影响报告（dependency_propagation.md §5）；
3. 若所有路线失效 → 命题语义状态**必须**离开 `true_in_scope`（转 `unknown` 或 `false_in_scope`），转换由事件自动提议、按 actor 权限确认；
4. 反例本身入 `research_log/counterexamples/`，不可删除。

---

## 6. 实现与测试对应

- 转换表：`core/state_machine/transitions.py`
- 非法转换异常：`IllegalTransition`
- 测试：`tests/test_state_transitions.py`（含非法升级、跨维度非法联动、冲突证据保留）
