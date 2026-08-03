# Run Contract — S0-T2 Sites starter 与独立项目边界

## 目标

在 Owner 明确授权下创建一个独立、仅 Owner 可见、未 Deploy 的 ChatGPT Sites 项目，为“胡楚靓工作台”记录真实 hosting linkage 与 D1/R2 binding 合同；随后从当前官方 Sites starter 建立可构建的本地项目边界。不制作产品 UI、不复制冻结 starter、不发布。

## 最小范围

- Owner 当前 ChatGPT Sites 会话中的新项目创建。
- `Personal-WorkBench/.openai/hosting.json`。
- 当前官方 Sites vinext starter、其 lockfile、运行时类型声明和 S0 配置守卫。
- `Personal-WorkBench/13_evidence/sites_shape.json` 与 `HANDOFF.md`。

## 授权与外部副作用

Owner 于 2026-08-03 明确授权“全部授权 不允许任何block”。本轮唯一外部副作用是创建一个新的私有 Site；不改变任何既有 Site、访问范围、Saved Version、Deploy、D1、R2、OAuth、邮件、Turnstile 或 Secret。

## 实际结果

- 已创建独立 Site，真实 linkage 已写入 `.openai/hosting.json`。
- 平台回执确认：D1=`DB`、R2=`FILES`、仅 Owner 可见、无外部成员、未部署、未发布。
- 因项目根已含 S0 文档，官方 `init-site.sh` 在隔离空目录运行；只合并 current vinext starter 与 lockfile，并保留已有 `.openai/hosting.json`。没有复制任务包内的跨框架 starter。
- 已执行并通过：`npm ci`、`npm run check`、`npm run build`、`npm test`。构建产物中的 `.openai/hosting.json` 与源配置逐字段一致。
- 为使当前 starter 的 Worker/D1 类型检查真实生效，按当前 Wrangler peer contract 固定 `@cloudflare/workers-types=4.20260515.1`，并通过 `Cloudflare.Env` 声明 `DB` / `FILES`。
- 静态隔离检查确认 hosting WeRead project ID 命中数为 `0`。当前仍仅为 starter 构建通过，不是产品 UI、Saved Version、身份服务或生产 PASS。

## 风险、回滚与停止条件

- 风险：把冻结跨框架 starter误当作当前 Sites starter，或误把 remote provision / starter build 叙述为产品或生产 PASS。
- 回滚：若 linkage 错误，只删除尚未部署的新 linkage；不得触碰既有 Site。远端 Site 删除需由 Owner 明确要求后再执行。
- 停止条件：Sites 不支持必要的全栈能力，或发现新 Site / binding 复用了 WeRead 资源时，停止 Save/Deploy 并回到 S0 对账。
- 本阶段已完成；S1 必须在新的 run 中开始，仍按“每个 run 至多一个阶段”推进。
