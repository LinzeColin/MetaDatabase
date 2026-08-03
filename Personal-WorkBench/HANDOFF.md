# Personal-WorkBench — S0 完成交接

## 当前目标

“胡楚靓工作台”已完成 Stage S0：独立私有 ChatGPT Sites 项目、真实 hosting linkage、D1/R2 binding 和可构建的当前官方 starter 均已建立并验证。下一 run 才能开始 S1 的视觉真值与获授权素材核验；本轮不制作产品 UI、不部署、不推送 GitHub。

## 当前状态

- 阶段：`S0_COMPLETE`
- 远端 Site：独立、仅 Owner 可见、无外部成员、未 Deploy / 未发布。真实 `project_id` 仅在 `.openai/hosting.json` 中；D1=`DB`、R2=`FILES`。
- 本地项目：当前官方 Sites vinext starter 与 `package-lock.json` 已同步。`npm ci`、`npm run check`、`npm run build` 和 `npm test` 全部通过；构建产物的 `.openai/hosting.json` 与源配置一致。
- 类型：`@cloudflare/workers-types=4.20260515.1` 与 `types/runtime-bindings.d.ts` 使 Worker/D1/R2 binding 的 TypeScript 检查真实生效。
- 当前开发分支：`codex/personal-workbench-s0`；整个任务包完成前不推送 GitHub。

## 已核验证据

- S0-T1 对账：`13_evidence/stage0_reconcile.json`。`origin/main`、本地 `main` 和 worktree 起点均为 `4a3efcffba10f318ac963377cd7cff046bcadb37`；未发现旧项目源码或历史实现。
- S0-T2：`13_evidence/sites_shape.json`。记录独立 Site、真实 binding、私有未部署状态、构建、artifact linkage 和证据边界。
- 任务包 SHA-256：210/210 通过。任务包原生 verifier 已以当前项目 lockfile 提供的 TypeScript 只读运行，结果为 `PASS_FOR_SEALED_TASKPACK`（19 个任务、15 条要求、42 个资产、47 项合同检查）；它不是当前 starter build 或产品验收的替代证明。
- 锁定安装报告 18 个依赖审计项（1 low / 4 moderate / 13 high）；未运行 `npm audit fix` 以避免未经评估地改写 lockfile。此项是后续质量/安全审查输入，不是生产安全 PASS。

## 冻结边界

- 当前 `app/_sites-preview/` 是官方可丢弃 starter loading skeleton，**不是**胡楚靓工作台 UI。S1 必须以冻结五张参考图、88px 左栏、粉白密度和已获授权 Hello Kitty 素材替换它；不得以 starter 外观交付。
- 不复用 WeRead 的 Sites、D1、R2、Secret、Saved Version 或发布版本。hosting 静态检查命中数为 `0`。
- Secret 仅在 Sites Settings；仓库、证据、聊天和 `.env.example` 不得包含实际值。本轮没有请求、接收或读取 Secret、Cookie、密码、Token、OAuth 值或用户数据。
- 不信任浏览器提交的 `user_id`；业务正文不得进入日志、status 或 Private-Database。
- S5 的 Save/Deploy、真实 Google / 邮件 / Turnstile、最终 Hello Kitty 权利记录、真实运营者资料和生产账户验收尚未开始。

## 下一步（新 run：S1）

1. 核验五张视觉参考、mask、`OWNER_APPROVAL.json` 与已获授权 Hello Kitty 素材的来源、用途、哈希和公开权利状态。
2. 在当前 vinext starter 中实现冻结页面骨架与设计 token；替换并移除官方 preview skeleton 与其元数据。
3. 在不启动 S2 的前提下，完成任务包要求的五页三轮视觉差分证据。

## 可复核命令

```bash
cd Personal-WorkBench
npm ci
npm run check
npm run build
npm test
python3 -m json.tool .openai/hosting.json >/dev/null
cmp -s .openai/hosting.json dist/.openai/hosting.json
git diff --check
```
