# Phase 1.1 — 测试基线报告（Task 1）

- 日期：2026-11-10（UTC）
- 分支：`audit/phase1-1`（基于 `main` @ `b322ae1`）
- 记录人：独立审计 Agent（Phase 1.1）
- **前置声明**：本报告只记录"测试在干净环境中通过"这一工程事实（`ESTABLISHED-IN-CODE`）。
  42 项测试通过 **不构成** 设计成立、理论成立或语义正确的证据（理论边界第 3、6 条）。

## 1. 环境（干净环境安装）

| 项 | 值 |
|----|----|
| 操作系统 | Linux 6.8.0-71-generic x86_64 |
| Python | 3.12.3 |
| 虚拟环境 | `.venv-audit`（`python3 -m venv` 全新创建，未复用 Phase 1 的 `.venv`） |
| pip | 24.0 |
| pytest | 9.2.0（pluggy 1.7.0） |
| jsonschema | 4.26.0 |
| referencing | 0.37.0 |
| jsonschema-specifications | 2025.9.1 |
| attrs | 26.1.0 |
| 运行时依赖 | **无**（core/ 仅用 Python 标准库；pytest/jsonschema 仅测试与校验用） |

安装命令（可重复）：

```bash
python3 -m venv .venv-audit
.venv-audit/bin/pip install pytest jsonschema
.venv-audit/bin/pytest -vv -o addopts=          # 全量
.venv-audit/bin/python examples/replay_demo.py           # 构建+写样本
.venv-audit/bin/python examples/replay_demo.py --replay  # 从样本恢复
```

## 2. 执行结果

完整逐项输出：`reports/phase1_1_baseline_pytest.txt`（42 行 PASSED 明细）。

```
platform linux -- Python 3.12.3, pytest-9.2.0, pluggy-1.7.0
rootdir: /home/ubuntu/RDE
configfile: pytest.ini
testpaths: tests
collected 42 items

tests/test_dependency_propagation.py ...........   11 passed  [ 26%]
tests/test_events.py .......                        7 passed  [ 42%]
tests/test_graph.py .......                         7 passed  [ 59%]
tests/test_state_transitions.py ..........         10 passed  [ 83%]
tests/test_versioning.py .......                    7 passed  [100%]

============================= 42 passed in 0.11s ==============================
```

| 指标 | 结果 |
|------|------|
| 测试总数 | 42（要求 ≥10，任务书 Task 7 的 7 类场景均有覆盖） |
| 通过 / 失败 / 跳过 | 42 / 0 / **0** |
| xfail / xpasses | 0（Phase 1 无预期失败） |
| replay_demo（构建模式） | 通过：哈希链校验 ✓、双次重放 digest 一致 ✓、影响报告输出正常 |
| replay_demo（`--replay` 模式） | 通过：从 `events_sample.jsonl` 恢复 digest 与构建时一致 |

## 3. 测试质量审查

### 3.1 跳过与弱化

- `grep -rn "skip\|xfail" tests/` → **无任何 skip/xfail 标记**。不存在"跳过即通过"。
- 弱断言模式扫描（`assert True` / `1 == 1` / 裸 `except: pass`）→ **零命中**。
- 两处 `assert ... is not None`（test_versioning.py:70-71）经人工复核：断言目的是
  "节点未被删除"（分叉后原/新对象都存在），同函数内另有 version/content 强断言，
  **判定为有效断言而非弱断言**。

### 3.2 执行顺序依赖

| 检查 | 命令 | 结果 |
|------|------|------|
| 逐文件独立运行 | 5 个文件分别单独执行 | 11+7+7+10+7 = **42**，全部通过 |
| 反序运行 | 文件倒序执行 | **42 passed** |
| 全量正序 | 默认顺序 | **42 passed** |

结论：无顺序依赖（每个测试通过 function 级 fixture 获得独立 RDE 实例）。

### 3.3 共享状态

- `tests/conftest.py` fixtures 均为默认 **function scope**（无 `scope=` 声明）；
- 无模块级可变全局（扫描 `RDE()/[]/{}` 顶层赋值 → 零命中）；
- 每个测试的事件日志、图状态随实例隔离。
- `conftest.py` 中的 `sys.path.insert` 为导入引导，不携带状态。

结论：**未发现共享状态污染**。

### 3.4 已知审查局限

- 本审查未覆盖"断言是否真的验证了设计语义"（弱断言的另一面：断言的是错误语义）。
  该项由 Task 2 对抗性审计与 Task 3 一致性表负责，不能由基线测试自查得出。

## 4. 基线结论

- ✅ 可重复：干净环境安装 → 全量通过 → 演示脚本通过，命令与版本如上可复现。
- ✅ 测试文件无跳过、无顺序依赖、无共享状态污染。
- ⚠️ 42/42 通过只证明 **实现符合 Phase 1 写下的规格**；
  规格本身是否正确、是否漏掉反例，见 `reports/adversarial_audit.md`。

相关文件：
- `.github/workflows/tests.yml`（push / pull_request 触发的 CI，Python 3.12 矩阵）
- `reports/phase1_1_baseline_pytest.txt`（完整逐项输出）
