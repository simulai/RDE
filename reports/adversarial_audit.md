# RDE Phase 1.1 — 对抗审计报告（T2）

- 分支：`audit/phase1-1`；审计环境：`.venv-audit`（Python 3.12.3 / pytest 9.2.0，全新虚拟环境）
- 方法：先以 13 项**对抗探针**（P1–P13）独立攻击现有实现，再固化为 **66 项对抗测试**
  （`tests/adversarial/`，覆盖 A 事件重放 / B 版本历史 / C 多路线 / D 证据冲突 / E 状态机权限 / F 图结构 / G schema 一致性）。
- 结果链路：**对抗测试首轮 51 通过 / 15 失败** → 逐项定性 → **最小修复**（仅拉回文档既有承诺，无功能新增）→
  对抗套件 **66/66 通过**，全量 **108/108 通过**（Phase 1 的 42 项原样保留，其中 1 项按文档设计修正期望，见 F-E03）。
- 日志：`reports/phase1_1_adversarial_pytest.txt`（66 项明细）、`reports/phase1_1_full_pytest.txt`（108 项）、
  `reports/phase1_1_baseline_pytest.txt`（Phase 1 基线 42 项）。

> **纪律声明**：所有修复都只把实现拉回 `docs/` 既有承诺（不改设计、不改北极星、不删历史、不升级假设为定理）；
> 每项修复在下表与正文均有记录；没有为了让测试通过而放松任何断言——恰恰相反，多项修复让实现更严格了。

## 0. 发现总表

严重度定义：**Major** = 违反文档承诺且可在真实研究使用中造成错误结论/历史损坏；**Medium** = 通路缺失、
schema/实现不一致、防御纵深缺口；**Low** = 观察项，设计未承诺但值得记录；**开放** = 代码层不可单方面修复，
需研究者裁决的设计缺口。

| ID | 领域 | 严重度 | 状态 | 一句话 |
|---|---|---|---|---|
| F-A01 | A 重放 | Medium | 仅记录（用法约束） | 裸 `replay()` 不校验哈希链，篡改日志可静默重放 |
| F-A02 | A 重放 | Medium | ✅ 已修复 | 入口不一致：`RDE(EventLog(verify=False))` 不做链校验；`RDE(list)` 直接崩溃 |
| F-A03 | A 重放 | **Major** | ✅ 已修复 | `_emit` 先写日志后应用：重复创建抛错时**事件已毒化日志**，引擎自身日志将不可重放 |
| F-B01 | B 版本 | **Major** | 开放（待研究者裁决） | 路线前提按 ID 解析到*当前*版本，无法钉住 v1；`definition_versions` 与路线解析漂移 |
| F-C01 | C 路线 | **Major** | ✅ 已修复 | 被 `invalidate_derivation` 撤销的路线仍被判 `intact`（`_route_status` 忽略路线自身 status） |
| F-C02 | C 路线 | **Major** | 开放（Q-007，设计层） | 隐藏前提：完全未声明 → 命题在报告中**不可见**；声明一半 → `still_valid` **假阳性** |
| F-D01 | D 证据 | Medium | ✅ 已修复 | `evidence_withdrawn` 事件类型与重放 handler 都在，但**没有引擎 API**，撤回路径不可达 |
| F-D02 | D 证据 | Medium | ✅ 已修复 | 引擎读取 `sufficiency` 决定 `insufficient`，但该字段不在 `evidence.schema.json` |
| F-E01 | E 权限 | **Major** | ✅ 已修复 | `agent:*` 可直接执行真值语义升级（违反原则 10 / architecture §5） |
| F-E02 | E 权限 | **Major** | ✅ 已修复 | 创建入口可直接携带未绑定的 `true_in_scope`（L1 只在转换时检查） |
| F-E03 | E 权限 | **Major** | ✅ 已修复 | L3 未实现：证明义务 `open` 的 Claim 可 `completed`；**既有测试与文档冲突，已按文档修正** |
| F-E04 | E 权限 | Medium | ✅ 已修复 | `agent` 可自评 `decision_effective=True` 且无外部验证引用（原则 10） |
| F-F01 | F 图结构 | Low | 仅记录 | 循环依赖静默终止，无"检测到环"警告（设计未承诺） |
| F-F02 | F 图结构 | Low | 仅记录 | 内容完全相同的重复关系被允许（唯一性只按 ID） |
| F-G01 | G schema | Medium | ✅ 已修复 | 多节点 `impact_report_generated` 的 `change.node` 是数组，但 schema 只允许 string |
| F-G02 | G schema | Low | 仅记录 | 多节点报告的 `kind` 被折叠为 `modified`（保真度损失） |
| F-G03 | G schema | Medium | ✅ 已修复 |（并入 F-D02：`sufficiency` 未入 schema） |

通过项（对抗探针确认无问题，均有对应绿测试）：哈希链篡改/调序/删事件/改 prev_hash 全部检出（A1–A5）；
哈希正确的未知事件被重放层拦截（A6）；哈希合法的非法状态转换被重放拦截（A7）；伪造经验轨升级被拦截（A7b）；
时间点回溯与分叉隔离（B1–B7）；真独立路线双向判定、`unjudgeable`、H-DEP-002 仅提议（C1/C4/C5/C6/C7）；
冲突不覆盖且必经 `invalidated` 中转、无删除路径（D1–D5、D8）；北极星三闸门（无 API + 重放拒绝 + schema 拒绝）；
`revise_node` 夹带状态字段被拒；超边多层传播、自环/循环有界终止、引用与类型混用检查、失效边不传播（F1–F9）；
样本日志与富场景事件全过 schema（G2）。

---

## 1. A — 事件与重放完整性

### F-A03（Major，已修复）— 失败的创建会毒化引擎自身日志
- **复现（修复前）**：`create_edge` 重复 ID → `ReplayError` 抛出，但 `EventLog.append` **已经先执行**——
  `_emit` 的顺序是 `log.append(...)` 然后 `apply(state, ev)`（`core/engine.py:_emit`）。
  此后 `replay(rde.log.events)` / `save()+restore()` 对**该引擎自己的日志**失败：日志里躺着一个必然重放失败的事件。
- **影响**：任何重复创建（节点/边/证据/推导/决策）都会把内存中的知识历史变成不可恢复状态；
  "事件溯源不允许覆盖"的防线（replay 层 `重复创建节点` 检查）反而成了自伤入口。
- **修复**：7 个创建入口（`create_node`/`create_edge`/`fork_definition`/`supersede`/`start_derivation`/
  `append_evidence`/`record_decision`）在写日志**之前**做存在性拒绝（`ValidationError`）。
  不变量由 `test_f04_duplicate_edge_id_rejected` 固化：被拒后日志长度、digest、可重放性均不变。
- **残余**：`_emit` 本身仍是"先写后应用"的非事务结构；本轮把所有已知会抛错的路径前置拦截，
  未来新增 handler 若再引入 apply 阶段抛错，同类风险会回归 —— 建议（不属本轮范围）后续把 `_emit` 改为
  先在副本上试应用、成功再提交。

### F-A02（Medium，已修复）— 入口校验不一致
- **复现（修复前）**：`RDE(EventLog(tampered, verify=False))` 构造成功（`RDE.__init__` 不校验传入的 `EventLog` 实例）；
  `RDE(list_of_events)` 直接 `AttributeError: 'list' object has no attribute 'events'`。
- **影响**：链校验是否发生取决于调用方选哪个入口 —— 防御纵深出现随机缝隙。
- **修复**：`RDE.__init__` 对任何载入形式统一 `verify_chain()`，并支持直接传 list（内部经 `EventLog(list)` 校验）。
  测试：`test_a08_tampered_log_rejected_at_all_entry_points`。

### F-A01（Medium，仅记录 / 用法约束）— 裸 `replay()` 不校验链
- **复现**：篡改事件内容后 `state_digest(replay(events))` 正常返回（确定性重放，不查哈希）；
  同一日志换序重放得到相同 digest（seq 是顺序权威）。`EventLog()` / `RDE` 入口则检出 `ChainBroken`。
- **影响**：绕过 `EventLog` 直接调用 `replay()` 的代码路径会失去完整性校验。
  当前代码中所有公开入口都先过链校验（F-A02 修复后），故仅为**用法约束**：
  `replay()` 是底层重放原语，不是校验入口。
- **固化**：`test_a10_replay_layer_documented_not_chain_checked`（明确记录两层职责）。
  建议：给 `replay()` 文档字符串加一行"不校验链，完整性请用 `EventLog.verify_chain()`"。

### 通过项（要点）
- 篡改中间事件内容 / 调换顺序 / 删除中间事件 / 改 `prev_hash` → `EventLog` 全部 `ChainBroken`（A1/A2/A4/A5）。
- 重复 seq → 重放 `ReplayError: 事件 seq 不连续`（A3）。
- 攻击者重算哈希插入未知事件 → 链通过（按设计：链只管完整性）但重放 `未知事件类型` 拦截（A6）。
- 攻击者插入哈希合法的 `proposed→completed`、`unknown→true_in_scope(empirical)` → 重放层
  `IllegalTransition` 拦截（A7/A7b）——重放确是第二重校验。

---

## 2. B — 版本与历史

### F-B01（Major，开放 —— 需研究者裁决版本钉住设计）
- **复现**（`test_b03_version_pin_gap_is_observable` / `test_c03_shared_definition_different_versions_indistinguishable`）：
  1. Claim 创建时记录 `definition_versions=[{definition-d1, v1}]`（正确：命题当时绑定 v1）；
  2. 修订 definition-d1 到 v2；`claim.definition_versions` **不会**被改写（正确，避免静默改写）；
  3. 但路线评估时 premise 按 **ID** 解析到图中**当前**节点（v2）——两条引用"不同版本"的路线无法区分，
     无 delta 的事后重查一律按 v2 判 `intact`，无法重建"当时绑定 v1"的判定。
- **影响**：与 `docs/design_risks.md` **R-017（版本引用漂移）/ Q-007（独立路线定义）**直接相关。
  缓解已存在：修订当刻的 `impact_report_generated` 会把受影响路线标 `broken`（`test_b02`），
  审计轨迹里留有"何时需复核"；但**修订之后**无法从路线自身重建当次判定。
- **处置**：不擅自重构（属依赖传播语义变更）。固化事实的测试以注释明确"该事实本身是缺口"；
  提交研究者裁决：是否在 derivation premise 上引入 `bound_versions`（或等价机制）。

### 通过项
- 旧 Derivation 内容逐字节不被改写；`state_at(seq)` 精确回溯 v1；历史栈按序保留（B1/B7）。
- 修订即发影响报告、引用旧版本的路线进复核视野（B2，原则 7）。
- 分叉双向隔离：改原不影响分叉、改分叉不影响原，各自历史独立（B4/B5）。
- 失效边保留可读但不再参与传播（B6，原则 8）。

---

## 3. C — 多证明路线语义

### F-C01（Major，已修复）— 撤销的路线不判失效
- **复现（修复前）**：`invalidate_derivation("derivation-d2")` 后，`_route_status(derivation-d2, …, delta=∅)`
  返回 `intact` → 命题仍 `still_valid`（`test_c07/c08` 首轮失败）。
- **根因**：`_route_status` 只在"前提本身是 derivation 且 status=invalidated"时判 broken，
  **从不检查被评估路线自身的 `status`**。
- **影响**：被撤销的证明继续充当有效路线 —— 直接违反 `state_semantics`（推导撤销即路线失效）与
  验收标准 5 的反面（失效路线不得支撑 still_valid）。
- **修复**：`_route_status` 首行检查 `route.status == "invalidated" → broken`。

### F-C02（Major，开放 —— Q-007 设计问题，代码层不可单方面修复）
两种表现形式（均以测试固化为**已知限制**，不作为正确性证据）：
1. `test_c02a_undeclared_hidden_premise_makes_claim_invisible`：隐藏前提完全不在任何元数据中 →
   受影响命题**根本不出现在影响报告**（也不在 unjudgeable）——报告的"未列出"被误读为"无影响"。
2. `test_c02b_..._false_positive`：命题依赖集登记了前提、路线 premises 漏登记 → 路线判 `intact` →
   `still_valid` 假阳性（尽管它逻辑上依赖被推翻的前提）。
- **影响**：路线独立性 = 按声明的前提集（H-DEP-001 已承认此前提）。元数据不完整时，
  传播分析的结论不可信。
- **兜底（已存在）**：即便假阳性，`action` 恒为 `review_routes`（不授予正确性，验收标准 5）——
  `test_c06_still_valid_never_grants_correctness` 同时证明：still_valid **不改变命题状态、
  不产生任何非 proposed 语义事件**。
- **处置**：提交研究者：是否需要"前提完备性审计"工具（如人工勾稽的元数据完备性检查），代码不猜。

### 通过项
- 真独立双路线双向判定；全灭 → `under_review`（C1）。
- broken + unknown → `unjudgeable`，reason 同时列出两类问题（C4，验收标准 10）。
- `modified` 类变化不产生语义离场提议；`refuted` 只产生 `proposed_only` 且要求
  `human_approval_granted`（C5，H-DEP-002）。
- 路线自身被撤销 → broken（C7/C8，修复后）。

---

## 4. D — 证据冲突与撤回/失效

### F-D01（Medium，已修复）— 撤回通路缺失
- **复现（修复前）**：`hasattr(rde, "withdraw_evidence") == False`；`evidence_withdrawn` 的事件类型、
  schema 枚举、重放 handler（`_evidence_withdrawn`）全部就位，唯独没有引擎 API —— 文档承诺的
  "撤回（source retraction）"路径**不可达**。
- **修复**：新增 `withdraw_evidence(evidence_id, *, reason, actor)`，镜像 `invalidate_evidence`：
  发 `evidence_withdrawn` → 经 `invalidated` 中转 → 按 `evidence_withdrawn` 驱动重算。
  测试 `test_d02_withdraw_one_side_via_withdraw_api`：mixed → 撤回反驳方 → `supported`，
  撤回的证据保留（`validity=withdrawn` + 仍在 `current_evidence` + 事件可回查）。

### F-D02 / F-G03（Medium，已修复）— `sufficiency` 字段不在 schema
- **复现（修复前）**：`core._recompute_evidence_state` 读 `evidence.get("sufficiency")` 决定
  `insufficient`，但 `schemas/evidence.schema.json` 无此属性 —— 实现私有机制，文档/schema 不可见。
- **修复**：schema 增补 `sufficiency: enum[sufficient, insufficient]`（带说明）；
  `test_d06` + `test_g03` 双重固化；`test_d07` 证明 insufficient 不被永久钉死（强证据可回到 supported）。

### 通过项
- 冲突 → `mixed`，双方保留；新增证据不因数量/方向坍缩（D1/D4，验收标准 6）。
- 离开 mixed 必经 `invalidated`：失效支持方 → `contradicted`，事件序列
  `none→supported→mixed→invalidated→contradicted`（D3，防覆盖护栏也被 `test_d09` 验证：
  证据状态不能由 `derivation_completed` 等逻辑事件驱动，逻辑/证据分离）。
- 全部失效 → `invalidated`；证据无删除路径，重放后节点仍在（D5/D8）。

---

## 5. E — 状态机与权限

### F-E01（Major，已修复）— Agent 直接授予语义状态
- **复现（修复前，探针 P1）**：`set_proposition_state(..., actor="agent:audit")` 把命题直接升为
  `true_in_scope` 成功 —— 违反原则 10 与 `architecture.md §5`（Agent 的自评只能是提议）。
- **影响**：经验路线的语义隔离（`docs` 中"逻辑路线才能产生语义状态"）在 actor 维度被绕过：
  任何 agent 标识都能给知识"盖章"。
- **修复**：非 human actor 对真值状态（`true/false_in_scope`）的**执行**必须拒绝，
  只能 `proposed_only=True` 写入提议（提议不改变状态）；human 才能执行。
  `test_e01` 同时验证三段：agent 执行拒 / agent 提议入日志且状态不变 / human 执行过。

### F-E02（Major，已修复）— 创建入口绕过 L1 绑定
- **复现（修复前，探针 E-create）**：`create_node(claim(..., prop="true_in_scope"))`，
  `assumptions=[]`、`scope="S"` 直接创建成功 —— 状态机的绑定检查只在 `set_proposition_state` 转换时执行。
- **影响**：原则 4/L1 形同虚设于创建路径；任何绕过转换 API 的写入（导入、未来批量工具）都能携带未绑定真值。
- **修复**：`validate_node`（创建与修订入口共用）对 `true/false_in_scope` 强制：
  非空 `assumptions` + 非空 `scope`，否则 `ValidationError`。
  `test_e02`/`test_e02b`：无绑定拒、有绑定过、空 scope 拒。

### F-E03（Major，已修复 + 既有测试按文档修正 —— 重点披露）
- **复现（修复前，探针 P2）**：`proof_obligations: status=open` 的 Claim 经 `formalized→active→completed`
  直接完成 —— `docs/state_semantics.md §4` 的 **L3（证明义务已满足才能 completed）完全未实现**。
- **冲突的既有测试**：`tests/test_state_transitions.py::test_work_state_cannot_jump_to_completed_via_engine`
  在 Phase 1 时**断言了这条违规路径成功**（"合法推进到 completed"）——即 42 项通过背后藏着一条
  与文档相反的期望（这正是"测试通过≠设计成立"的实例）。
- **修复**：
  1. `set_work_state`：Claim → `completed` 前，全部 `proof_obligations` 必须 `discharged/withdrawn`，否则
     `IllegalTransition("L3: …")`；
  2. `validate_node`：创建入口同检（堵住 `create_node(work="completed")` 直接携带）；
  3. **既有测试按文档设计修正**：保留原跳跃拒绝断言，新增 L3 拒绝断言，再经内容修订回填义务
     （`revise_node({"proof_obligations": [...status=discharged]})`，版本化留痕）后完成。
     —— 这是**向文档靠拢的收紧**，不是放松；此处按纪律显式披露。义务状态变更走内容修订是当前
     既定机制（无独立义务 API，属可选后续改进）。
- **测试**：`test_e05`/`test_e05b` + 修正后的 phase1 用例。

### F-E04（Medium，已修复）— Agent 自评决策有效性
- **复现（修复前，探针 P11）**：`backfill_decision(..., decision_effective=True, actor="agent:audit")`
  成功且无外部验证引用。
- **修复**：`decision_effective is not None` 时要求 `actor=="human"` **或** 非空 `external_validation_ref`。
  `test_e06` 三段：agent 无引用拒 / agent 带外部引用过 / human 过。

### 通过项（权限边界确认）
- 北极星三闸门：无修改 API；手工 `log.append("north_star_modified", actor=human)` 也被重放拒绝
  （第一阶段禁令）；schema 层 `actor` 非 human 直接不合格（`test_e03`）。
- 伪造"人类签署"的非法历史（blocked→completed）在重放层 `IllegalTransition`（`test_e04`）。
- `revise_node` 夹带 `proposition_state/work_state/evidence_state` 被拒（`test_e07`，原则 6 的入口检查）。
- **边界确认**：agent 允许推进**流程性**工作状态（proposed→formalized），但不得签发人类授权、
  不得授予语义状态（`test_e08`）—— 权限修复没有把 agent 变成"什么都不能做"。

---

## 6. F — 图结构

### F-F01 / F-F02（Low，仅记录）
- 循环依赖（A↔B）与自环在有界时间内终止（实测 <1ms），双方都在报告视野内，但**没有**
  "检测到环"的显式警告 —— 设计文档未承诺，记为观察项（`test_f02` 注释固化）。
  实际传播靠 visited 集合去重，行为是"静默截断"。
- 内容完全相同、ID 不同的重复关系被允许（唯一性仅按 ID）——`test_f04b` 固化。
  是否需要内容指纹/去重语义，留研究者裁决。

### 通过项
- 两前提汇合两结论再下传第二层（超边多层，`test_f01`）。
- 引用不存在节点拒；空端点拒（`test_f05`）。
- `entails×evidential`、`supports×logical`、未知类型全拒（代码 + schema 双闸门，`test_f06`/`test_g04`）。
- 归档前提 → 路线 broken；归档节点仍可解析（无删除，`test_f07`）。
- `depends_on` 方向语义：基础变化向依赖者传播、反向不传播（`test_f07b`）。
- 失效边保留但不传播（`test_f08`）；引擎与 `EventLog` 无任何删除 API（`test_f09`）。
- （F-A03 修复后）重复创建以 `ValidationError` 在写日志前拒绝，日志零污染（`test_f04`）。

---

## 7. G — Schema 与实现一致性

### F-G01（Medium，已修复）— 多节点影响报告不合 schema
- **复现（修复前，探针 P4）**：`impact({"d1":"modified","d2":"refuted"})` 产生的
  `impact_report_generated.change.node` 是 `["d1","d2"]`（`propagate` 对 Δ 集合本来就如此构造，
  算法文档明确 Δ 是多元组），但 `event.schema.json` 把 `change.node` 定为 `string` → 校验失败。
- **影响**：批量变化的影响报告无法通过 schema 校验（CI/导入校验会误报）；schema 与实现漂移。
- **修复**：`change.node` 放宽为 `oneOf[string, array<string> minItems 1]`；
  `test_g01`（多节点）/`test_g01b`（单节点）/`test_g02b`（富场景逐事件）。

### F-G02（Low，仅记录）
- 多节点报告的 `kind` 被硬折叠为 `"modified"`（`propagate` 对 Δ>1 的实现），即使其中含 `refuted` ——
  报告保真度损失。修复需要 kind 映射逻辑，留后续（不影响正确性判定，`propagated` 逐条条目仍带各自信息）。

### 通过项
- `examples/events_sample.jsonl` 全部事件过 schema（`test_g02`，0 不合格）。
- 证据 `sufficiency` 已入 schema（F-D02 修复）；边类别混用 schema 层拦截（`test_g04`）；
  ID 前缀规则 `def-` 拒、`definition-` 过（`test_g05`）。

---

## 8. 对抗探针原始记录（修复前）

| 探针 | 攻击 | 修复前结果 |
|---|---|---|
| P1 | agent 直接执行语义升级 | ⚠️ 成功 → F-E01 |
| P2 | 义务 open 的 Claim completed | ⚠️ 成功 → F-E03 |
| P3 | 查找撤回 API | ⚠️ 不存在 → F-D01 |
| P4 | 多节点 impact 过 schema | ⚠️ `node is not of type 'string'` → F-G01 |
| P5 | 样本日志全量过 schema | ✅ 0 不合格 |
| P6 | 裸 replay 篡改日志 | ⚠️ 不察觉 → F-A01（记录） |
| P7 | 版本钉住 | ⚠️ 漂移存在（修订当刻有报告标记）→ F-B01（开放） |
| P8 | 循环依赖 | ✅ 0.1ms 终止（无环警告 → F-F01） |
| P9 | 重复关系 / 自环 | ⚠️ 内容重复允许（F-F02）/ ✅ 自环终止 |
| P10 | sufficiency 入 schema | ⚠️ 缺 → F-D02 |
| P11 | agent 自评决策有效 | ⚠️ 成功 → F-E04 |
| P12 | insufficient 通路 | ✅ 工作正常 |
| P13 | 北极星 agent 事件 | ✅ 重放拒绝 + schema 拒绝 |

## 9. 修复清单（全部为最小改动，均含回归测试）

| # | 文件 | 改动 | 对应发现 |
|---|---|---|---|
| 1 | `core/engine.py` | `__init__` 统一 `verify_chain()` + 支持 list 载入 | F-A02 |
| 2 | `core/engine.py` | 7 个创建入口写日志前存在性拒绝 | F-A03 |
| 3 | `core/engine.py` | `set_proposition_state` 非 human 真值执行拒绝 | F-E01 |
| 4 | `core/graph/__init__.py` | `validate_node`：真值绑定 + Claim L3 创建检查 | F-E02/F-E03 |
| 5 | `core/engine.py` | `set_work_state`：Claim completed 的 L3 检查 | F-E03 |
| 6 | `core/engine.py` | `backfill_decision` 原则 10 守卫 | F-E04 |
| 7 | `core/engine.py` | 新增 `withdraw_evidence` | F-D01 |
| 8 | `core/dependency_analysis/__init__.py` | `_route_status` 检查路线自身 invalidated | F-C01 |
| 9 | `schemas/evidence.schema.json` | 增补 `sufficiency` | F-D02 |
| 10 | `schemas/event.schema.json` | `change.node` string∨array | F-G01 |
| 11 | `tests/test_state_transitions.py` | L3 语义修正（见 F-E03 披露） | F-E03 |

## 10. 未修复项（如实列出，不隐藏）

1. **F-B01 路线版本钉住** —— 语义级变更，需研究者在 `bound_versions` 方案间裁决（R-017/Q-007）。
2. **F-C02 隐藏前提** —— 设计开放问题（Q-007），代码不可"检测不存在的声明"；兜底是
   `review_routes` 强制人工复核 + 元数据完备性要求。
3. **F-A01 裸 `replay()` 无链校验** —— 用法约束已文档化并测试固化。
4. **F-F01 环警告 / F-F02 内容去重 / F-G02 多节点 kind 保真** —— Low 观察项，设计未承诺。
5. **`_emit` 非事务** —— 本轮前置拦截了全部已知毒化路径；结构性事务化列为后续建议。
