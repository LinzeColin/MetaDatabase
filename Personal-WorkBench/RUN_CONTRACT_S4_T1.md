# Run Contract — S4-T1 无障碍/响应式/性能本地基线

## 目标

补齐 Personal-WorkBench 的本地可验证 S4-T1 基线：触控可达性、键盘焦点可见性、响应式保护与无障碍行为检查，形成可复用的质量采样脚本和证据。

## 最小相关范围

- `app/globals.css`：按钮/输入/导航控件触控目标、焦点态与 `prefers-reduced-motion`。
- `scripts/verify-quality.mjs`：静态质量扫描、无障碍与性能采样。
- `package.json`：新增 `test:quality` 脚本入口。
- `13_evidence/quality.json`：本次 S4-T1 的质量证据。
- `13_evidence/visual/manifest.json`：沿用上一阶段 `test:visual` 的阶段证明。

## 明确不在本 run 的范围

- 不做真实云端认证/会话的真实运行链路。
- 不承诺 Saved Candidate 与生产发布门禁变更。
- 不改动租户数据库 schema、运行时绑定或资产授权策略。

## 验收与停止条件

- `npm run test:quality` 必须通过并生成 `13_evidence/quality.json`（状态 `PASS_LOCAL_QUALITY`）。
- `npm run test:visual` 通过且保留现有 `13_evidence/visual/manifest.json`。
- 若出现 `verify-quality` 证据 `FAIL_LOCAL_QUALITY`，禁止切入下一任务。

## 结果（本 run）

- 阶段状态：`PASS_LOCAL_QUALITY`（局部路径 + API 响应基线通过）
- 关键证据：
  - `13_evidence/quality.json`
  - `13_evidence/visual/manifest.json`（本地视觉阶段 `PASS`）
- 下一步：按任务包路线推进 S4-T2（离线/故障模式与降级策略本地验证）。
