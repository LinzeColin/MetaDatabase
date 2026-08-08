# Run Contract — S4-T2 离线重放与故障降级本地基线

## 目标

在不改动主视觉基线和任务包接口契约的前提下，补齐离线/故障场景的可恢复行为：本地待发队列的读取、追加、重放与异常中断逻辑应可复用且可验证。

## 最小相关范围

- `app/_components/workbench/outbox-queue.ts`：提炼 `outbox` 的可复用与可测逻辑（读写、追加、重放、异常停滞）。
- `app/_components/workbench/todo-page-client.tsx`：将离线队列读写与重放流程改为调用共享 outbox 模块，统一冲突/503/网络异常退避。
- `tests/outbox-replay.test.mts`：离线重放行为回归测试（全成功、冲突、503、网络异常）。
- `scripts/verify-offline-replay.mts`：本地可执行验证入口，生成 `13_evidence/resilience.json`。
- `package.json`：新增 `test:resilience` 脚本。

## 明确不在范围（本 run）

- 不触及真实跨设备数据库同步回放（此为后续生产环境演练）。
- 不变更 `server` API 合同、认证渠道、R2 权限或 OAuth/邮件真实验证链。

## 验收与停止条件

- `npm run test:resilience` 通过，生成 `13_evidence/resilience.json`，状态为 `PASS_LOCAL_RETRY_RESILIENCE`。
- `npm run test:resilience` 中的重放脚本应覆盖：
  - 成功重放会清空已完成队列；
  - 冲突、503、网络异常会停止处理并保留未成功条目；
  - 不会无条件清空待发队列。
- 若验收项任一失败，不进入下一阶段。

## 当前结果（本 run）

- 阶段目标：`PASS_LOCAL_RETRY_RESILIENCE`
- 已完成项：离线模块抽取、测试、验证脚本与命令接入。
- 待输出证据：
  - `13_evidence/resilience.json`（`PASS_LOCAL_RETRY_RESILIENCE`）
