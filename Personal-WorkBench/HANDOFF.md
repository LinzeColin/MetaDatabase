# Personal-WorkBench — S0 交接

## 当前目标

在 `MetaDatabase/Personal-WorkBench/` 承接“胡楚靓工作台”v0.0.0.8 的后续开发。当前只推进 Stage S0：建立独立的 ChatGPT Sites 项目和可复核的 hosting linkage；不启动 S1，不制作或替换产品 UI，不部署。

## 当前状态

- 阶段：`S0_IN_PROGRESS`
- `S0-T1`：已完成语义对账，证据在 `13_evidence/stage0_reconcile.json`。
- `S0-T2`：远端私有 Site 已创建。真实 `project_id` 只记录于 `.openai/hosting.json`；D1=`DB`、R2=`FILES`；仅 Owner 可见；无外部成员；未 Deploy / 未发布。
- 当前 worktree 尚未同步 Sites 的当前 starter 源码或 lockfile。因此 S0-T2 所要求的 `npm ci`、`npm run check`、`npm run build` 均为 `NOT_RUN`，S0 不可称为构建 PASS 或 Stage complete。
- 当前开发分支：`codex/personal-workbench-s0`；按 Owner 指令，在整个任务包完成前不推送 GitHub。
- 任务包权威源：`/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8`。

## 已核验证据

- `SHA256SUMS.txt`：210/210 个条目匹配。
- 原生入口 `python3 -B 12_scripts/verify_taskpack.py` 已运行，但不是 PASS：本机缺少 `tsc`，唯一报告错误为 `TypeScript strict 失败: [Errno 2] No such file or directory: 'tsc'`。
- 因此任务包 SHA-256 完整性为 `PASS`；完整封包验证为 `NOT_PASS_DUE_TO_LOCAL_TOOLCHAIN`，不得写成产品、Saved Candidate、供应商或生产 PASS。
- S0-T1：远端 `origin/main`、本地 `main` 与此 worktree 起点均为 `4a3efcffba10f318ac963377cd7cff046bcadb37`；未发现已跟踪的 `Personal-WorkBench` 源码或历史实现。
- S0-T2：`13_evidence/sites_shape.json` 保存远端创建回执的范围、真实 binding、私有状态、未部署状态、无 WeRead 复用和本地 build 限制。

## 冻结边界

- 保持五张截图、Hello Kitty、固定左侧导航、页面密度与粉白视觉真值；禁止重做 UI 或替换角色视觉。
- 后续必须使用独立 ChatGPT Sites 项目；不得复用 WeRead 的 Sites、D1、R2、Secret 或发布版本。
- Secret 只允许进入 Sites Settings；不得放入仓库、证据、聊天或 `.env.example`。本轮没有请求、接收或读取 Secret、Cookie、密码、Token、OAuth 值或用户数据。
- 不信任浏览器提交的 `user_id`；用户正文不得进入日志、status 或 Private-Database。
- 公开 Deploy 仍不可执行：S5 的 Save/Deploy、真实 OAuth / 邮件 / Turnstile、最终 Hello Kitty 权利材料和运营者信息均未完成验收。

## 下一步

下一个 run 仍先完成 S0：将 **当前** Sites 推荐 starter 安全同步到此 worktree，取得 lockfile 后执行 `npm ci`、`npm run check`、`npm run build`，并将实际结果写入 `13_evidence/sites_shape.json`。不得用占位脚本、未锁定依赖或封包内跨框架 starter 冒充当前 Sites build。

仅在 S0 的 linkage、隔离和可构建性都有实证后，才可在**新的** run 启动 S1。

## 可复核命令

```bash
python3 -m json.tool Personal-WorkBench/.openai/hosting.json >/dev/null
python3 -m json.tool Personal-WorkBench/13_evidence/sites_shape.json >/dev/null
rg -n -i 'weread' Personal-WorkBench/.openai Personal-WorkBench/13_evidence
git diff --check
git status --short -- Personal-WorkBench
```
