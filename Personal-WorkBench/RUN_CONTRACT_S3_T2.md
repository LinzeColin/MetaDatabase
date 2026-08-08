# Run Contract — S3-T2 全部业务模块云端适配（本地基线）

## 目标

在保持页面骨架与 `?reference=` 冻结结构不变的前提下，补齐“全部业务模块”级别的本地可验证适配链路：基础 CRUD 矩阵、离线/重放语义占位、以及二设备可读性的第一步本地契约。

## 最小相关范围

- `app/page.tsx`、`Personal-WorkBench` 核心 UI 结构保持不变；先以服务端数据模型与测试层做接口适配基线。
- `server/data/`, `server/files/`、`app/api/workbench/`：继续使用 tenant-first、session-first、幂等键、R2 私有对象键与审计约束。
- `tests/`：新增 `module-matrix.test.mjs` 与 `e2e-smoke.test.mjs`，脚本入口 `npm run test:modules` 与 `npm run test:e2e`。

## 明确不在范围（本 run）

- 不做前端大规模交互重写，不改造全部组件状态管理与离线写队列 UI。
- 不进行真实 Saved Candidate、真实 Google/邮件/Turnstile、A/B 跨设备联网联调。
- 不触及公开 Deploy 与版权素材授权。

## 验收与停止条件

- `npm run test:modules` 与 `npm run test:e2e` 本地通过（均为本地回归基线）。
- 生成 `13_evidence/module_matrix.json`，标明：
  - CRUD 本地可验证；
  - 租户隔离不跨用户；
  - 真实二设备重放与冲突提示仍为后续任务预备条件。
- `13_evidence/module_matrix.json` 状态在本 run 为 `PASS_LOCAL_SQLITE_SMOKE`。

## 结果（本 run）

- 状态：`PASS_LOCAL_SQLITE_SMOKE`
- Saved Candidate：`NOT_RUN`
- 公开 Deploy：`BLOCKED_ASSET_RIGHTS`
- 记录来源：
  - `13_evidence/module_matrix.json`（`PASS_LOCAL_SQLITE_SMOKE`）
  - `13_evidence/ui_structure.json`（`PASS_LOCAL_REFERENCE_SMOKE`）
