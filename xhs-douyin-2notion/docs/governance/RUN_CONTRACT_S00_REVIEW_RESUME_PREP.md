# Run Contract — RUN-X2N-S00-REVIEW-RESUME-PREP

## 目标

为 `INC-X2N-S00-P05-001` 建立不含 Secret、账号标识、Remote URL、本机路径或自由文本的 Owner 恢复证明入口，消除从 Owner Action 到 `STG.X2N.0.REVIEW.RESUME` 之间的口头歧义。

本 Run 是 Stage 0 Review Fix，不执行新的 DAG Task。完成它不代表 Owner 已执行恢复动作，不改变 `G0_BLOCKED_OWNER_ACTION`，不授权 push、Stage 1、产品代码或真实系统调用。

## 最小范围

- Repo：恢复回执 Schema、合成 Fixture、Owner-only 生成器、fail-closed verifier、单测和 Review 文档。
- Private Runtime：只登记逻辑路径 `runtime/owner_recovery_attestation.local.json`；本 Run 不创建真实回执。
- Owner 输入：必须由 Owner 在当前任务中明确选择一种已完成动作，之后才可调用生成器。

## 非目标

- 不接收、读取、打印或保存凭据值、Cookie、账号、Remote URL 或 Provider 页面截图。
- 不替 Owner 轮换、撤销、重新认证或证明过期。
- 不签发 G0，不修改 Gate/Task State，不上传，不进入 Stage 1。

## Owner 动作枚举

1. `rotated_and_revoked_old_material`
2. `reauthenticated_and_revoked_old_material`
3. `confirmed_old_material_expired`
4. `retained_shared_external_material_with_x2n_zero_contact`：仅在 Owner 明确要求保留共享材料、接受外部残余风险，并禁止 x2n 接触或改变该材料时使用；必须同时满足 `CE-X2N-20260720-S00-REVIEW-RESUME` 的补偿控制。

只有 Owner 直接声明其中一项已经完成后，才允许使用固定确认语句调用：

```bash
python3 -B scripts/record_owner_recovery.py \
  --action <owner-selected-action> \
  --owner-confirmation I_CONFIRM_INC_X2N_S00_P05_001_OWNER_DECISION_IS_FINAL
```

禁止 Agent 根据 `gh auth status`、本地扫描 0 命中、当前可登录或临时 clone 已删除来推断 Owner Action 已完成。

## 验收

```bash
python3 -B -m unittest tests.test_owner_recovery_attestation
python3 -B scripts/verify_owner_recovery_attestation.py
```

- 回执缺失：第二条命令退出 `2`，状态只能是 `BLOCKED_OWNER_ACTION`。
- 回执畸形、含 Secret 形态、时间倒置、Action/State 不一致或试图授权 G0/Stage 1/upload：退出 `1 / FAIL_CLOSED`。
- 回执合法：退出 `0 / PASS`，但只给出 `STAGE_0_REVIEW_RESUME_ONLY`；G0 仍为 `BLOCKED_PENDING_REVIEW_RESUME`。
- 后续独立 `STG.X2N.0.REVIEW.RESUME` 必须重跑完整私有根、仓库、事件、历史 Phase 与 G0 验证，才能决定是否更新 Gate。

## 风险、回滚与停止条件

- 风险：Owner 自述不是 Provider Secret，也不是凭据值；它只记录 Owner 已确认的生命周期动作，或“保留外部共享材料＋x2n 零接触”的明确风险决策。
- 回滚：反向提交本 Review Fix；不得删除 Owner 私有回执或伪造替代回执。
- Stop：无 Owner 直接声明、回执不合法、出现任何敏感值、外部 worktree 重叠或既有 Stage 0 回归失败时，维持 G0 阻断。
