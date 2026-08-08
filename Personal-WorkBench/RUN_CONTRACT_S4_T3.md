# Run Contract — S4-T3 冻结 Candidate 准备验收

> 历史说明：此文件记录原 S4-T3 的 Builder 本地预检，不能构成正式 15/15 裁决。由于冻结任务包的 Saved Candidate 证据循环，后续执行顺序由 [PWB-S4-S5-SEQUENCE-001](./ACCEPTANCE_SEQUENCE_ADDENDUM.md) 约束：先完成 `S4-T3A` 独立就绪审查，再在私有 Candidate 采证，最后由 `S6-T1` 做正式独立验收。

## 目标

在不改动现有可运行架构与视觉真值的前提下，建立 S4-T3 所需的验收预检：
- 统一 Builder 证据格式为“无裁决权（NOT RUN）”；
- 执行任务包冻结态基础校验；
- 产出 `npm run verify:release` 与 `13_evidence/verifier.json`，并进入下一阶段前给出明确阻断项。

## 最小相关范围

- `scripts/verify-release.mjs`：执行任务包冻结与本地验收预检，写入 `13_evidence/verifier.json`。
- `package.json`：新增 `verify:release` 命令。
- `RUN_CONTRACT_S4_T3.md`：本阶段本地完成标准记录。
- `HANDOFF.md`：切换当前阶段为 S4-T3。
- `13_evidence/verifier.json`：由 `verify:release` 生成的当前阶段证据文件。

## 明确不在范围（本 run）

- 不触发 Saved Candidate 与生产 Deploy 的真实 OAuth/邮件/Google/Turnstile 运行。
- 不自行判定正式 Verifier 的 PASS（`13_evidence/verifier.json` 需保持不可误判为正式裁决）。
- 不代替 S5 阶段的 Owner 私钥/域名/回滚/二次设备真实联调。

## 验收与停止条件

- `npm run verify:release` 成功执行并写入 `13_evidence/verifier.json`。
- `13_evidence/verifier.json` 显式记录：
  - 本地可复跑证据链（quality/visual/resilience）
  - taskpack 冻结自检结果
  - 未与正式 Verifier 裁决混淆
- `python3 12_scripts/verify_taskpack.py`（在 taskpack 源目录）通过 `PASS_FOR_SEALED_TASKPACK`。
- 若出现环境边界阻断（Saved Candidate/生产回归未授权），状态应为环境阻断而非产品 PASS。
- 若任务无法进入下一阶段，`HANDOFF.md` 必须标注最短阻断项和下一可执行动作。
