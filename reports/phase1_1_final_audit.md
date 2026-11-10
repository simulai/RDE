# RDE Phase 1.1 — 独立审计最终判定（T5）

- 分支 `audit/phase1-1`；日期 2026-11-10；证据链：
  `reports/phase1_1_baseline.md`（T1）→ `reports/adversarial_audit.md`（T2）→
  `reports/design_impl_consistency.md`（T3）→ `experiments/UCS/import_audit.md`（T4）→ 本报告。

## 判定：**PASS WITH LIMITATIONS**（有条件通过）

不是 FAIL：十项验收标准在独立反例攻击下全部成立；发现的 11 项"实现与文档冲突"全部以最小修复
拉回文档承诺并有回归测试；没有掩盖任何开放问题。
不是 PASS：审计发现 Phase 1 的"42 项全绿"**不等于设计成立**——其中一项既有测试甚至断言了一条
违反文档 L3 的路径（见答 1/答 3）；且存在 3 项代码层不可单方面修复的开放设计问题与 1 项未实现的
文档规则（L2）。

---

## 六问六答

### 1. 现有设计与代码是否经得住独立反例审计？

**经得住核心验收，但"经得住"的范围必须限定。**

- 十条验收标准（任务书 §11）在 13 项对抗探针 + 68 项对抗测试攻击后**全部成立**：
  哈希链/重放双层可检出篡改、调序、删事件、哈希合法的非法历史注入；版本回溯与分叉隔离成立；
  真独立路线双向判定成立；冲突证据必经 `invalidated` 中转不被覆盖；报告如实输出 unjudgeable。
- 但审计同时抓出 **15 项缺陷**（1 Major 毒化日志 + 5 Major 语义/权限缺口 + …），证明
  "42 项通过"只说明**当时被测到的路径**成立。最典型的反例：Phase 1 既有测试
  `test_work_state_cannot_jump_to_completed_via_engine` 曾**断言**证明义务 `open` 的 Claim 可以
  `completed`——直接违反 `state_semantics.md L3`。测试通过 ≠ 设计成立，本轮用事实复现了这句话。
- 审计后仍开放（代码层不可单方面修复，见答 4）：**Q-007 隐藏前提**、**R-017 版本钉住**、
  **L1 边界张力**。这三项是"设计尚未解决"，不是实现 bug——如实上报，不以测试绿灯掩盖。

### 2. 实现与文档是否一致？（明细见 `design_impl_consistency.md`）

| 分类 | 条数 |
|---|---|
| 已实现且测试覆盖 | 26 |
| 已实现但未充分测试 | 4 |
| 仅文档设计 | 6（L2 版本确定检查、假设升级规则、反例自动落盘、schema 演进、多 Agent、因果边） |
| 实现与文档冲突 | 12（**11 条本轮已修复并披露**，1 条=L1 路线存在性子条件开放） |
| 设计尚未解决 | 5（Q-007、R-017、L1 边界、Q-EDGE-001、R-014/Q-011 规模） |

修复均为最小改动（11 处，见对抗审计 §9），无功能新增、无语义变更、无历史删除；
其中 F-A03（`_emit` 先写后应用导致失败创建毒化日志）是审计中发现的最严重工程缺陷，
修复后以"被拒创建日志零污染"不变式固化（`test_f04`）。

### 3. 测试是否足以支撑"验收成立"的声明？边界在哪？

- **基线（T1）**：全新 `.venv-audit` 干净环境下 Phase 1 = 42 passed / 0 failed / 0 skipped /
  0 xfail；无弱断言模式；倒序执行一致；函数级 fixture 无顺序耦合（`phase1_1_baseline.md`）。
- **本轮后**：全量 **117 passed**（Phase 1 原 42 + 对抗 68 + UCS 完整性 7），
  CI 工作流 `.github/workflows/tests.yml` 同步覆盖（pytest 双 demo + schema 解析）。
- **边界声明（不可越过的解释红线）**：
  1. 测试通过 = 实现符合**文档所写的设计**；它不能证明设计本身正确（答 1 的三项开放问题天然无法
     由现有测试判定）；
  2. 既有测试中 1 项期望被按文档修正（L3，已在对抗审计 F-E03 显式披露）——除该处外未改动任何
     既有断言，也未为了让测试通过而放宽任何预期；
  3. `xfail/skip` 数为 0；已知限制采用"文档化测试"（固化事实 + 注释标明是缺口而非正确性证据），
     不用绿灯伪装成结论。

### 4. 已知限制与开放问题清单（不隐藏）

**需研究者裁决（Major，阻塞"设计已成立"的声明）**
1. Q-007 隐藏前提：未声明的前提不可检测——报告"未列出"≠"无影响"；现有兜底是
   `review_routes` 强制人工复核（`c02a/c02b` 固化）。
2. R-017 版本钉住：路线前提按 ID 解析到当前版本，无法钉住 v1（`b03/c03` 固化）；
   现有缓解是修订当刻的影响报告标记。
3. L1 边界：文档要求真值前置"存在 completed 推导路线"，但该子条件未实现（`e09` 固化），
   且与 refute 反例离场路径存在张力——严格实现会否封死原则 5 需裁决。

**仅文档/第二阶段**：L2 未实现（`e10` 固化）、假设升级规则、反例自动落盘、schema 演进
（Q-ARCH-001）、多 Agent、因果边（Q-EDGE-001）、规模压测（R-014/Q-011）。

**低危观察**：裸 `replay()` 无链校验（用法约束，F-A01）、循环无环警告（F-F01）、
内容重复边允许（F-F02）、多节点报告 kind 折叠（F-G02）、`_emit` 建议事务化（F-A03 残余建议）。

**测试覆盖缺口**：merge/回溯组合语义、混合 Δ 保真、随机事件序列属性测试（U1–U4）。

### 5. UCS 第一个真实研究项目的数据导入是否就绪？

**就绪为"草案导入"（draft-import），不就绪为"完整定义"。**

- 四件交付齐备：`experiments/UCS/definitions.json`（8 条件，名称逐字来自任务书）、
  `experiments/UCS/hypotheses.json`（28 个关系假设槽位，Hypothesis 节点形态，**0 条 entails 边**）、
  `experiments/UCS/import_audit.md`（导入/未导入/待确认全记录）、
  `examples/ucs_research_graph.json`（36 节点 / 0 边，可直接载入 RDE）。
- 纪律全部落实并由 7 项完整性测试（U01–U07）强制：全部 `unknown/none/proposed`、
  无 `entails` 关系边、2^8=256 仅作封闭空间计数、不预设单调、缺失处一律【待人工确认】标记。
- **待人工确认清单 6 项**（import_audit §6）：条件完整定义、28 槽位关系类型/方向/依据、
  是否新增 hypothesis 节点类型、五类约束中哪些真实存在、Phase 1 占位文件处置、
  真实研究材料的引用方式。在这些确认完成前，本导入**不得**被引用为任何 UCS 研究结论。

### 6. 最终判定与进入下一阶段的前置条件

**判定：PASS WITH LIMITATIONS。**

进入第二阶段（或对 Phase 1 出具正式签收）前建议满足：

1. **研究者裁决三项开放设计问题**（答 4 之 1–3），裁决结果回写 `docs/` 并各配测试；
2. **L2 落地或明示推迟**：要么实现 proposed→formalized 的定义版本确定检查，要么在
   `state_semantics.md` 标注其阶段归属；
3. **UCS 待确认清单过半**（至少条件定义 + 关系类型清单由人类确认）后才谈"真实数据导入完成"；
4. **规模压测基准**（R-014/Q-011）在第二阶段启动前定义；
5. （工程建议，非阻塞）`_emit` 事务化、环警告、事件序列属性测试按优先级排入。

---

## 附：本分支变更清单

| 类别 | 内容 |
|---|---|
| 报告 | `reports/phase1_1_baseline.md`、`phase1_1_baseline_pytest.txt`、`adversarial_audit.md`、`design_impl_consistency.md`、`phase1_1_adversarial_pytest.txt`、`phase1_1_full_pytest.txt`、`phase1_1_final_audit.md`（本文件） |
| 测试 | `tests/adversarial/`（A–G 六域 + UCS 完整性，共 75 项新测试）；既有测试仅 1 项按文档修正（L3，已披露） |
| CI | `.github/workflows/tests.yml`（push/PR 触发，pytest + demo + schema） |
| 修复 | `core/engine.py`（入口链校验、创建前置拒绝、F-E01/E03/E04 守卫、`withdraw_evidence`）、`core/graph/__init__.py`（L1/L3 创建入口）、`core/dependency_analysis/__init__.py`（F-C01）、`schemas/evidence.schema.json`（sufficiency）、`schemas/event.schema.json`（多节点 Δ） |
| 数据 | `experiments/UCS/{definitions,hypotheses}.json`、`import_audit.md`、`examples/ucs_research_graph.json` |
| 文档 | `README.md`（仓库结构、Test A 状态）、`.gitignore`（`.venv-*/`） |
