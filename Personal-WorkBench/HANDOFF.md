# Personal-WorkBench — 只读准备交接

## 当前目标

在 `MetaDatabase/Personal-WorkBench/` 承接“胡楚靓工作台”v0.0.0.8 的后续开发；本轮仅建立项目入口和读取任务包，不启动 `PURSUING_GOAL`，不创建 ChatGPT Sites 项目，也不写业务实现。

## 当前状态

- 阶段：`S0_IN_PROGRESS`
- 本轮任务：`S0-T1` 目标仓语义对账；语义对账已记录，但完整任务包 Verifier 仍受本机 `tsc` 缺失阻断，因此 S0 尚未完成。
- 下一任务：`S0-T2` Sites starter 与独立项目边界；当前为 `BLOCKED`，因为尚未有 Owner 创建的私有 Sites 项目/非敏感 `project_id`。专用创建接口可能返回短期源仓凭据，按安全边界未调用。
- 本地项目根：`Personal-WorkBench/`（由 Owner 于 2026-08-03 指定）
- 当前开发分支：`codex/personal-workbench-s0`；按 Owner 指令，在整个任务包完成前不推送 GitHub。
- 任务包权威源：`/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8`
- 任务包声明状态：`SEALED_TASKPACK` / `SEALED_FOR_BUILD_LAST_MILE_NOT_DEPLOYED`
- 本轮没有复制 `05_prebuild/starter-kit`，没有创建应用代码、依赖、环境变量、数据库或外部资源。

## 已核验证据

- `SHA256SUMS.txt`：210/210 个条目匹配。
- 原生入口 `python3 -B 12_scripts/verify_taskpack.py` 已运行，但结果不是 PASS：本机缺少 `tsc`，唯一报告错误为 `TypeScript strict 失败: [Errno 2] No such file or directory: 'tsc'`。
- 因此只能把任务包的 SHA-256 清单完整性记为已验证；完整封包验证状态为 `NOT_PASS_DUE_TO_LOCAL_TOOLCHAIN`，不得写成产品、Saved Candidate、供应商或生产 PASS。
- S0-T1 对账证据：`13_evidence/stage0_reconcile.json`。远端 `origin/main`、本地 `main` 与此 worktree 起点均为 `4a3efcffba10f318ac963377cd7cff046bcadb37`；未发现任何已跟踪的 `Personal-WorkBench` 源码或历史实现。
- 官方 Sites 文档的只读核验确认：推荐 starter、D1 持久化数据、R2 文件对象、外部身份提供商、私有 Save Version → Deploy 的两阶段流程和 Settings 内 Secret 都与冻结架构一致；账户/区域/工作区权限与实际 runtime 反馈仍为 `UNKNOWN`。

## 已冻结的范围与边界

- 保持五张截图、Hello Kitty、固定左侧导航、页面密度与粉白视觉真值；禁止重做 UI 或替换角色视觉。
- 后续必须是独立 ChatGPT Sites 项目；不得复用 WeRead 的 Sites、D1、R2、Secret 或发布版本。
- 不信任浏览器提交的 `user_id`；用户正文不得进入日志、status 或 Private-Database。
- 秘密只允许进入 Sites Settings；不得放入仓库、证据、聊天或 `.env.example`。
- 公开 Deploy 仍被阻断：未获得最终授权 Hello Kitty 原始素材、真实运营者信息、Google/邮件/Turnstile 生产链路和明确生产授权前，只允许私有候选阶段。

## 尚未获得的环境绑定输入

1. 目标仓/现有源码与最新 integration base 的语义对账来源（S0-T1）。
2. ChatGPT Sites 创建、D1、R2、Save 的 Owner 权限（S0-T2 起）。
3. 最终获授权 Hello Kitty 原始素材及权利记录。
4. Google OAuth、事务邮件、Turnstile 的真实配置（仅未来由 Owner 在 Sites Settings 注入）。
5. `LEGAL_OPERATOR_NAME` 与 `PRIVACY_CONTACT_EMAIL`。

## 下一步与停止条件

S0-T1 已按 19 项 DAG 完成一次分类；详见 `RUN_CONTRACT_S0_T1.md` 和 `13_evidence/stage0_reconcile.json`。`S0-T2` 的最小解除动作：Owner 在 ChatGPT Sites 中新建一个只限 Owner/管理员访问、未 Deploy 的独立项目，并只提供其不敏感 `project_id`；不得提供 token、Secret、Cookie 或密码。之后在下一个独立 run 核验推荐 starter 与绑定边界。

在 `S0-T2` 之前，不得部署、不得请求或接收凭据、不得创建/修改真实 Sites、D1、R2、OAuth、邮件或 Turnstile 资源，也不得把任务包内的演示/私有素材作为公开素材使用。

## 可复核命令

```bash
PACK='/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8'
(cd "$PACK" && shasum -a 256 -c SHA256SUMS.txt)
(cd "$PACK" && python3 -B 12_scripts/verify_taskpack.py)
git status --short -- Personal-WorkBench
```
