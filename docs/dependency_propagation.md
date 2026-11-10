# 依赖传播（Dependency Propagation）— Task 5

文档版本：v0.1 ｜ 状态：算法为 `DESIGN-DECISION`，独立性判定依据为 `H-DEP-001`（**待验证**，开放问题 Q-DEP-001）

## 1. 输入与输出

**输入**：变化的基础节点集合 `Δ`（定义修改、假设推翻、定理修订、证据失效）及其变化类型（`modified` / `refuted` / `withdrawn` / `superseded`）。

**输出**：结构化影响报告（本身也是一个事件 `impact_report_generated`）：

```json
{
  "change": {"node": "assumption-A1", "kind": "refuted", "seq": 42},
  "directly_affected": ["claim-C1", "derivation-D1", "..."],
  "propagated": [
    {"node": "claim-C1", "kind": "claim",
     "status": "still_valid",           // 仍有至少一条完好推导路线
     "routes_broken": ["derivation-D1"],
     "routes_intact": ["derivation-D2"],
     "action": "review_routes"},
    {"node": "claim-C2", "kind": "claim",
     "status": "under_review",          // 所有路线均受影响
     "routes_broken": ["derivation-D3"],
     "routes_intact": [],
     "action": "recheck_required"},
    {"node": "experiment-E1", "kind": "evidence_conclusion",
     "status": "needs_interpretation",  // 实验结论需重新解释
     "action": "reinterpret"}
  ],
  "still_valid": ["claim-C1", "claim-C4", "..."],
  "route_stopped": ["research-line-L2"],   // 应停止的研究路线（blocks 链）
  "unjudgeable": [{"node": "claim-C9", "reason": "缺少依赖元数据"}]
}
```

报告**必须**包含"仍有效集"与"无法判定集"（验收标准 10：系统能明确报告自己无法判断的事项）。

## 2. 图遍历方向

沿**结构/逻辑依赖方向**的逆向？不——沿**被依赖方向**正向传播：

- `depends_on`: X depends_on Y ⇒ 从 Y（基础）正向到达 X；
- `entails`: P entails C ⇒ 从 P 正向到达 C；
- `derived_from`: derivation derived_from premises ⇒ 从 premise 正向到达 derivation；
- `supports`/`tests`（证据类）：从证据失效到达命题 → 只影响证据状态路径，**不**直接进入语义状态；
- `blocks`：阻塞链正向传播 → `route_stopped`。

## 3. 算法（四步）

### Step 1 — 下游可达集
BFS/DFS 从 `Δ` 出发，沿 §2 的边方向收集受影响节点集合 `R`（含路径，用于报告可追溯性）。

### Step 2 — 按对象分类
把 `R` 中节点按类型分桶：`Claim` / `Derivation` / `Evidence·Experiment` / `Question·Decision` / `Definition·Assumption` / 其他。

### Step 3 — **证明路线聚合**（核心，验收标准 4/5）

对每个受影响 `Claim C`：

```
routes(C) = { d : d ∈ Derivation, d.conclusions 包含 C }   # 所有推导路线
for d in routes(C):
    premises(d) = d.derived_from 前提集（含其依赖的定义/假设版本）
    broken(d)   ⇔ premises(d) ∩ Δ ≠ ∅   或 d 的前提中有任一前提当前
                  语义状态离开 true_in_scope（假设被推翻/定义被取代）

intact(C)   = { d ∈ routes(C) : ¬broken(d) }
if intact(C) ≠ ∅:            status(C) = still_valid      # 单路线失效不推翻结论
elif routes(C) = ∅:           status(C) = no_derivation_metadata  → unjudgeable
else:                        status(C) = under_review     # 全部路线失效，必须复核
```

**规则**：`still_valid` **不等于**"证明仍正确"——它只表示"尚有一条未被本次变化命中的路线"，报告中的 action 固定为 `review_routes`（人工/外部复核），不得自动升级为已验证（原则 10、边界 8）。

### Step 4 — 证据与执行维度的联动
- 实验结论（`tests`/`supports` 边的来源端变化）→ `needs_interpretation`（只提请重新解释，不自动改证据状态）；
- `Question`/`Decision` 被 `blocks` → `route_stopped`；
- 类型未知/元数据缺失 → `unjudgeable`（显式报告，不猜测）。

## 4. 示例：基础假设被推翻

```
前提：claim-C1 有两条路线 D1、D2；D1 premises={A1, def-X}，D2 premises={A2, def-X2}（不共享 A1）
      claim-C2 只有路线 D3，premises={A1}
变化：A1 被推翻（refuted）

结果：
  C1 → still_valid（D1 失效，D2 完好）→ action=review_routes
  C2 → under_review（唯一路线失效）  → action=recheck_required
  依赖 def-X 的其他命题 → 依其路线情况同理
不会出现：C1 被自动推翻 —— 违反验收标准 5 即为算法失败（测试 test_dependency_propagation.py）
```

## 5. 反例驱动的自动状态离场（原则 5 与验收标准 5 的张力）

当 `status = under_review` 且变化类型为 `refuted`：

- 系统**提议** `proposition_state_changed: true_in_scope → unknown`（事件 `proposed` 化），并要求按 actor 权限确认；
- 有 `intact` 路线时**禁止**自动提议离场（除非法变更范围绑定被破坏——此时按 scope 精确处理：`true_in_scope` 的 scope 收窄而非状态离场）。

> 这段"提议 vs 执行"的边界是 `H-DEP-002`（待验证），第一阶段实现为：默认只生成提议事件，`human_approval_granted` 后执行。

## 6. 复杂度与规模

- Step 1–2：O(V+E)（超边按 premises×conclusions 展开计）；
- Step 3：对每个受影响 Claim O(routes × |premises|)；
- 最坏情况（高度共享基础节点）：可达集近全图 → 需要增量缓存/分层（**未解决** Q-DEP-002，规模风险 R-014）。第一阶段正确性优先，不做剪枝优化（原则 1）。

## 7. 独立性判定的开放问题（Q-DEP-001）

"两条路线独立"的当前定义仅是**前提集合不相交于 Δ**，这不等于认识论独立：

- 两条路线若共享未被标记的假设（元数据缺失）→ 误报 `still_valid`；
- 两条路线若共享同一定义但该定义被"细化"而非"推翻"→ 边界情况未定义。

已知缓解：前提集必须显式列出（Claim 字段 `依赖节点`、Derivation 字段 `derived_from`）；缺失 → 归入 `unjudgeable` 而非默认完好。**这仍是假说 H-DEP-001 的主要风险点。**

## 8. 测试对应

`tests/test_dependency_propagation.py`：基础节点修改、下游传播完整性、多证明路线（单路线失效不推翻）、元数据缺失 → unjudgeable、影响报告事件落盘。
