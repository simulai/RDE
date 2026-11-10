# 事件溯源（Event Sourcing）— Task 4

文档版本：v0.1 ｜ 状态：`DESIGN-DECISION`；哈希链完整性为 `H-ES-001`（**待验证**：能防静默覆盖，但不防拥有写权限的合谋者——见 design_risks R-010（对应 H-004））

## 1. 真相源

事件日志（JSON Lines，append-only）是唯一真相源。知识状态 = 事件的**纯函数**重放结果：

```
KnowledgeState = fold(replay, initial_state, events_in_sequence_order)
```

任何对节点/边/状态的修改都必须先转化为事件；读模型（`core/graph`）不接受绕过事件的写入。

## 2. 事件公共结构

```json
{
  "event_id": "evt-0000000007",
  "seq": 7,
  "type": "node_created",
  "timestamp": "2026-01-01T00:00:00Z",
  "actor": "human|agent:<id>|system",
  "target": ["claim-…"],
  "payload": { },
  "prev_hash": "…",
  "hash": "…"
}
```

- `seq`：单调序号，重放顺序的权威（**不用** wall-clock 排序，避免并发不确定性）；
- `prev_hash`/`hash`：SHA-256 哈希链，任何历史条目被改动都会断链（`verify_chain()`）；
- `actor`：审计主体（原则 9/10 的执行依据）。

## 3. 事件类型目录（第一阶段）

| 类别 | 类型 | 说明 |
|------|------|------|
| 结构 | `node_created` | 创建节点（含类型、版本 v1、scope、source） |
| 结构 | `node_version_created` | 新版本（内容变化），旧版本不改 |
| 结构 | `edge_created` / `edge_validity_changed` | 建边；边失效/被取代 |
| 版本 | `superseded` / `fork_created` | 版本取代；Fork Definition（M6） |
| 状态 | `proposition_state_changed` | 语义状态转换（payload 必含 justification/assumptions/scope） |
| 状态 | `evidence_state_changed` | 证据状态转换（由证据类事件驱动） |
| 状态 | `work_state_changed` | 执行状态转换 |
| 证据 | `evidence_appended` / `evidence_invalidated` / `evidence_withdrawn` | 追加/失效/撤回（**无删除**） |
| 推导 | `derivation_started` / `derivation_completed` / `derivation_invalidated` | 数学轨 |
| 影响 | `impact_report_generated` | 依赖影响报告落盘为事件/Artifact（M5） |
| 分支 | `branch_created` / `branch_merged` / `branch_pruned` / `question_reopened` | M6 |
| 决策 | `decision_recorded` | M7（目标、选项、理由、预算、预期价值、结果、有效性回填） |
| 授权 | `human_approval_granted` | 人类授权（北极星/目标修改前置） |
| 预留 | `north_star_modified` | 仅 schema 预留，第一阶段禁止发出 |
| 日志 | `replay_checkpoint` | 可选重放校验点（派生数据，可重建） |

## 4. 如何从事件日志恢复研究状态（重放）

```
replay(events):
    state = empty_state()
    for e in sorted(events, key=seq):
        assert e.hash_chain_valid(e.prev_hash)
        handler = HANDLERS[e.type]          # 未知类型 → 显式失败，不静默跳过
        state = handler(state, e)           # 纯函数；不读时钟、不读外部
    return state
```

**确定性要求**（验收标准 1）：

1. 排序只依赖 `seq`；
2. handler 不读 wall-clock、不读随机数、不依赖 dict 迭代顺序差异（结果按 ID 排序输出）；
3. 同一日志 → 字节级相同的状态摘要（`state_digest()` 比对）；
4. 未知事件类型 = 重放失败（防止"跳过不认识的历史"造成静默偏差）。

## 5. 两种典型变更的处理

### 5.1 定义修改（不静默改变旧版本）

```
1. node_version_created(def, v2, content_hash=v2)   # v1 原样保留
2. edge_validity_changed(依赖 v1 的边 → superseded)  # 显式失效，不删除
3. dependency_analysis → impact_report_generated     # 下游影响报告（验收标准 7）
4. （若 v1 仍需引用）旧事件不变；读取历史状态 = 只重放到当时的 seq（时间点重建）
```

- 旧版本回溯：`state_at(seq=N)`（重放前 N 条）→ 验收标准 2 的实现方式；
- 任何旧版本内容都可从"截至其被取代时点的事件"重建，没有静默覆盖（验收标准 2 测试 `test_versioning.py`）。

### 5.2 证据追加（单调累积）

```
evidence_appended(e1 → claim_A)   → evidence_state_changed(A: none→supported)
evidence_appended(e2 → claim_A)   → evidence_state_changed(A: supported→mixed)   # 冲突保留
evidence_invalidated(e1, reason)  → 重算 → (A: mixed→contradicted)               # 显式失效而非删除
```

- 证据**永不删除**，只有 `invalidated`/`withdrawn`（带原因与 actor）；
- 冲突产生 `mixed`，不会因后续单条证据而静默变回 `supported`（对应状态表规则）。

## 6. schema 演进（开放问题 Q-ARCH-001）

事件 payload 的向后兼容策略**第一阶段未定**。当前措施：`event.schema.json` 只做最低限度约束，`payload` 允许按 `type` 细分（`oneOf`）；新增事件类型必须同时登记到本文 §3 表格。版本化事件 envelope（`schema_version` 字段）已预留但未启用——**待决**。

## 7. 与测试的对应

- `tests/test_events.py`：追加、哈希链校验、未知类型失败、`state_digest` 确定性；
- `tests/test_versioning.py`：时间点重建、旧版本回溯、定义分叉；
- 重放一致性（验收标准 1）：`test_events.py::test_replay_consistency`.
