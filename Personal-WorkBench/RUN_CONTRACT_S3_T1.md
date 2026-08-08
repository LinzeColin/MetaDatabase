# S3-T1 Run Contract — 旧数据预览与迁移

## 目标

在不影响原始本机副本前提下，实现旧 IndexedDB 导出数据的预览与幂等导入。

## 最小范围

- `server/data/legacy-import.ts`：校验、预览生成、幂等入库流程。
- `app/api/workbench/legacy-import/{preview,apply}/route.ts`：会话后置的 API 接口。
- `server/http/api.ts`：LegacyImport 错误码映射。
- `tests/legacy-import.test.mts`：预览/导入/重复/失败路径回归。
- `package.json`：`test:legacy-import`。
- `13_evidence/legacy_import.json` 与 `HANDOFF.md` 关键变更更新。

## 关键不在范围

- 跨设备同步状态管理与隐私同意开关（`S4/S3-T2/3`）。
- 真实网络故障、429/500、离线重试的生产级演练（`S4`）。
- 对图片清单资源对象的二进制回填恢复。

## 验收与停止条件

- 本地可验证：
  - `npm run test:legacy-import`
  - `npm run test:schema`
  - `npm run lint`
  - `npm run typecheck`
  - `npm run verify:assets`
- 阶段成功标准：预览/导入重复路径无重复行；重复提交不产生新记录；不满足输入结构拒绝。
- 未通过任一验收项则暂停：
  - 旧记录导入成功前不改变服务端状态；
  - 断网/重试会导致重复写入；
  - 旧版本 payload 写入成功。

## 当前状态

- 目标状态：`PASS_LOCAL_CONTRACT`
- Saved Candidate：`NOT_RUN`
- 公开 Deploy：`BLOCKED_ASSET_RIGHTS`（与 S2 保持一致）

## 预期证据

- `13_evidence/legacy_import.json`
  - `status: PASS_LOCAL_CONTRACT`
  - 记录可重放、重复提交、不变更本机副本（本地逻辑）

## 交接建议

- 进入下一任务前需在任务包说明中确认 `S3-T2`/`S4` 阶段边界：跨设备同步与生产级并发/重试策略。
