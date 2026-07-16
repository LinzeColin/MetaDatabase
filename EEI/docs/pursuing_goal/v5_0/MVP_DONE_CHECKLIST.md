# MVP Done 七条核对清单（v0.1.0 tag 前置）

- prepared_at: `2026-07-16T18:50:00+10:00`
- 依据: `V5_0_ROOT_LOCK.yaml mvp_done_definition`
- 用法: S11PCT02 打 tag 前逐条核对；`OPEN` 项闭合后此表转 `READY`。

| # | 条款 | 状态 | 证据指针 |
|---|---|---|---|
| 1 | 211 验收矩阵 P0 全闭（A202/A204/A205/A209/A026/A027/A108-A112；A210 以 D2 记录替代） | **OPEN**（A204 窗 07-17 闭；A205/A209 待 Owner release-manager 合并一审；其余已 real：A202 签核包、A026/A027 金标 DONE、A210 豁免签名在包内） | artifacts/operator_inputs/a202_a210_signed_release_decision_bundle_20260715.json；artifacts/tests/a205/t1303_release_manager_activation_preflight.json；CURRENT.yaml open_evidence_windows |
| 2 | release-ready validator、make verify、四包、新仓 CI 全 PASS | PASS（每 PR 复核；tag 时四包终重生成） | eei-validation CI #27-#38 全绿；Makefile verify 链 |
| 3 | 16/16 模块 active 且各有 E2E；黄金纵切全为真实已发布事实 | PASS | S8PCT02（PR #21）；GV-FACT-001/002 生产库上线（PR #8） |
| 4 | 数据平台：2016+ 回看、采集连续 7 天、备份恢复演练 | **OPEN**（仅 7 天窗：本机 S7PDT02 07-23 闭）；2016+ ✓（2191 份全年份）；备份恢复 ✓（51 表对拍并实战用过） | S7PDT01（PR #12）；S7PDT03 演练；CURRENT.yaml 窗注册 |
| 5 | 云端 7×24：生产 URL 全功能、cron 连续 7 天 run_log、home 入口、移动一致 | **OPEN**（仅云 7 天窗 07-23 闭）；URL ✓ eei.linzezhang.com；home ✓；移动 ✓（375 零横溢）；小时级心跳已加密证据 | S10 全阶段（PR #30-#35）；GET /v1/cloud/runs |
| 6 | 观感：十要素 ≥8 + ADP 十模式全对照 + 动效 bar 八项（证据留存） | PASS | S9-GATE（PR #29）：docs/pursuing_goal/v5_0/S9_GATE_EVIDENCE.md + runtime_evidence/EEI/s9_gate/ |
| 7 | 三文件与 canonical facts 同步、v0.1.0 tag + CHANGELOG | **OPEN**（tag 为最后动作；三文件每 PR 同步中；CHANGELOG 已预置） | 开发记录.md/功能清单.md/CURRENT.yaml；CHANGELOG.md |

## 剩余闭合路径（全部时间/Owner 级）

1. **2026-07-17**：A204 24h 探针窗闭 → 收割 7 心跳汇总 → 向 Owner 出「A209 治理闭环 + A205 激活」合并审包 → Owner 签核后条款 1 闭。
2. **2026-07-23**：双 7 天窗闭 → CLOUD-GATE 收割 → 条款 4/5 闭。
3. 之后：S11PCT02 四包终重生成 + 本表全 PASS 核对 + tag v0.1.0 + CHANGELOG 定稿 → 条款 2/7 闭 → **MVP Done**。
