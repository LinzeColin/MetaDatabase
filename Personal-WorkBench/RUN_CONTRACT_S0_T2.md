# Run Contract — S0-T2 Sites starter 与独立项目边界

## 目标

在 Owner 明确授权下创建一个独立、仅 Owner 可见、未 Deploy 的 ChatGPT Sites 项目，为“胡楚靓工作台”记录真实 hosting linkage 与 D1/R2 binding 合同；不制作产品 UI、不复制冻结 starter、不发布。

## 最小范围

- Owner 当前 ChatGPT Sites 会话中的新项目创建。
- `Personal-WorkBench/.openai/hosting.json`。
- `Personal-WorkBench/13_evidence/sites_shape.json` 与 `HANDOFF.md`。

## 授权与外部副作用

Owner 于 2026-08-03 明确授权“全部授权 不允许任何block”。本轮唯一外部副作用是创建一个新的私有 Site；不改变任何既有 Site、访问范围、Saved Version、Deploy、D1、R2、OAuth、邮件、Turnstile 或 Secret。

## 实际结果

- 已创建独立 Site，真实 linkage 已写入 `.openai/hosting.json`。
- 平台回执确认：D1=`DB`、R2=`FILES`、仅 Owner 可见、无外部成员、未部署、未发布。
- 静态隔离检查应保证 WeRead project ID 命中数为 `0`。
- 当前 worktree 尚无同步回来的当前 Sites starter 或 lockfile，故 `npm ci`、`npm run check`、`npm run build` 均为 `NOT_RUN`；不得把此远端创建回执写成构建通过。

## 风险、回滚与停止条件

- 风险：把冻结跨框架 starter 误当作当前 Sites starter，或误把 remote provision 叙述为本地 build PASS。
- 回滚：若 linkage 错误，只删除尚未部署的新 linkage；不得触碰既有 Site。远端 Site 删除需由 Owner 明确要求后再执行。
- 停止条件：Sites 不支持必要的全栈能力，或发现新 Site / binding 复用了 WeRead 资源时，停止 Save/Deploy 并回到 S0 对账。
- 本阶段不触发 S1；后续仍按“每个 run 至多一个阶段”推进。
