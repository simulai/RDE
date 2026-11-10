# CONTRIBUTING

## 铁律

1. **正确性优先于效率。** 提交前跑通 `pytest tests/ -q`。
2. **不制造理论确定性。** 未被证明的判断必须标 `H-xxx`（假说）或 `Q-xxx`（待决），登记到 `docs/design_risks.md` 与 `docs/epistemic_status.md`。
3. **不虚构实验结果。** UCS/W3/TRVC 的任何数字、结论、图表必须有可追溯来源；W3 未获 pilot 批准前不得写入任何结果；TRVC 已有结论不得重新解释或篡改。
4. **历史不可静默覆盖。** 事件日志 append-only；修改历史必须是显式事件并可审计。禁止 rebase 后 force-push 已共享的主分支历史。
5. **逻辑与证据分离、证明与经验分离。** 提交不得引入把 `supports` 当 `entails` 用的字段或代码路径。
6. **状态转换表只在 `core/state_machine` 修改**，且必须同步更新 `docs/state_semantics.md` 与对应测试。
7. **理论边界九条**（README §2）不得被任何文档、注释、PR 描述违反。
8. **重大研究目标修改需人类授权**，以 `human_approval_granted` 事件记录。

## 提交流程

1. 新增主张 → 先查 `docs/falsification_criteria.md` 有无对应失败判据；没有的主张改为开放问题。
2. 代码改动 → 附测试；文档改动 → 附边界一致性自查。
3. PR 描述包含：动机、影响的转换表/事件类型、测试清单、本 PR 引入或关闭的 H/Q 编号。

## 审计

`research_log/audits/` 记录审查结论。自我评价不能替代外部验证（理论边界第 8 条）：审计条目须注明审查者身份（human / external / agent，agent 审计不授予状态升级）。
