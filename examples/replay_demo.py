#!/usr/bin/env python3
"""事件日志重放演示（验收标准 1：同一日志 → 同一知识状态）。

用法：
    python examples/replay_demo.py            # 构建示例研究状态，写出 events_sample.jsonl 并验证
    python examples/replay_demo.py --replay   # 读取已提交的 events_sample.jsonl 重放验证

演示内容（结构性示例，不含任何真实实验结论）：
1. 定义 / 假设 / 命题 / 两条推导路线 / 证据；
2. 推翻假设 → 影响报告（一条路线失效、结论仍有效、另一命题需复核+提议）；
3. 冲突证据 → mixed；
4. 日志落盘 → 恢复 → 独立重放两次 → 摘要一致 + 哈希链校验。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import RDE, replay, state_digest  # noqa: E402

TS = "2026-01-01T00:00:00Z"
SAMPLE = Path(__file__).parent / "events_sample.jsonl"


def build() -> RDE:
    rde = RDE()

    def node(nid, ntype, **kw):
        base = {"id": nid, "type": ntype, "version": 1, "created_at": TS,
                "source": {"origin": "human"}, "scope": kw.pop("scope", "示例范围"),
                "content": kw.pop("content", nid)}
        base.update(kw)
        return base

    def claim(cid, routes, deps, asums):
        return node(cid, "claim", routes=routes,
                    definition_versions=[{"id": d, "version": 1} for d in deps],
                    assumptions=[{"id": a, "version": 1} for a in asums],
                    dependency_nodes=deps + asums,
                    proof_obligations=[{"id": f"po-{cid}", "statement": "占位义务",
                                        "track": "mathematical", "status": "open"}],
                    falsification_conditions=["占位反证条件"],
                    current_evidence=[], proposition_state="unknown",
                    evidence_state="none", work_state="active",
                    next_research_action={"action": "占位下一步", "decision_ref": None})

    rde.create_node(node("definition-d1", "definition", scope="全局"))
    rde.create_node(node("definition-d2", "definition", scope="全局"))
    rde.create_node(node("assumption-a1", "assumption"))
    rde.create_node(node("assumption-a2", "assumption"))
    rde.create_node(claim("claim-c1", ["derivation-d1", "derivation-d2"],
                          ["definition-d1"], ["assumption-a1"]))
    rde.create_node(claim("claim-c2", ["derivation-d3"],
                          ["definition-d1"], ["assumption-a1"]))
    for did, premises, concl in [
        ("derivation-d1", ["assumption-a1", "definition-d1"], "claim-c1"),
        ("derivation-d2", ["assumption-a2", "definition-d2"], "claim-c1"),
        ("derivation-d3", ["assumption-a1", "definition-d1"], "claim-c2"),
    ]:
        rde.start_derivation(node(did, "derivation", premises=premises,
                                  concludes=[concl], track="mathematical",
                                  status="draft", work_state="active"))

    # 证据：先支持后冲突 → mixed（验收标准 6）
    rde.append_evidence(node("evidence-e1", "evidence", evidence_kind="experimental",
                             validity="valid", supports=["claim-c2"], contradicts=[]))
    rde.append_evidence(node("evidence-e2", "evidence", evidence_kind="experimental",
                             validity="valid", supports=[], contradicts=["claim-c2"]))
    return rde


def main() -> int:
    if "--replay" in sys.argv:
        rde = RDE.restore(SAMPLE)
        print(f"[replay] 从 {SAMPLE.name} 恢复：digest={rde.digest()[:16]}…  事件数={len(rde.log)}")
    else:
        rde = build()
        rde.save(SAMPLE)
        print(f"[build]   digest={rde.digest()[:16]}…  事件数={len(rde.log)} → 写入 {SAMPLE.name}")

    # 1) 哈希链完整（历史不可静默覆盖）
    rde.verify()
    print("[check]   哈希链校验通过")

    # 2) 同一日志独立重放两次 → 同一状态
    d1, d2 = state_digest(replay(rde.log.events)), state_digest(replay(list(reversed(rde.log.events))))
    assert d1 == d2 == rde.digest(), "重放不一致！"
    print(f"[check]   重放一致性通过（两次独立重放 digest 相同：{d1[:16]}…）")

    # 3) 推翻假设 → 影响报告
    if rde.graph.require("assumption-a1")["proposition_state"] != "false_in_scope":
        rde.refute("assumption-a1", note="演示：反例推翻")
    report = rde.state["reports"][-1]
    print(f"\n[impact]  变化: {report['change']}")
    for e in report["propagated"]:
        extra = ""
        if "routes_broken" in e:
            extra = f" | broken={e['routes_broken']} intact={e['routes_intact']}"
        if "proposed_state_change" in e:
            extra += " | 提议状态离场(待人类批准)"
        print(f"  - {e['node']}: {e['status']} (action={e.get('action')}){extra}")
    print(f"  仍有效: {report['still_valid']}")
    print(f"  无法判定: {report['unjudgeable']}")

    c2 = rde.graph.require("claim-c2")
    print(f"\n[epistemic] claim-c2: 命题状态={c2['proposition_state']} 证据状态={c2['evidence_state']}"
          "  ← 冲突证据保留为 mixed（未被覆盖）")
    print("\n完成。注意：以上全部为结构性演示，不含任何真实实验结论。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
