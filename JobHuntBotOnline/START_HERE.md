# JobHuntBot Online v0.3.0 SaaS｜Codex 最后一公里入口

## 先做什么

0. **先读 `OWNER_WALKTHROUGH_20260811.md`** —— 2026-08-11 线上独立走查的实测结果，
   里面写明了第 3 条说的「第一处真实断点」到底在哪，以及今天只该做的那一件事。
1. 读取 `PURSUING_GOAL.txt`、`AGENTS.md`、`taskpack/CANONICAL_CONTRACT.md`、`taskpack/task_dag.json` 和 `taskpack/acceptance_contract.json`。
2. 只读观察 `LinzeColin/MetaDatabase` 最新 `main`、分支 `codex/jobhuntbot-online-v020-deployment`、真实 OVH/Coolify、域名、PostgreSQL、SMTP、DeepSeek Secret、Private-Database、R2 和 status。
3. 从第一处真实断点执行 Task DAG；不要重新研究产品方向，也不要用整包覆盖仓库中更新且更好的实现。

## 当前事实

- 产品版本：`0.3.0`；任务包修订：`0.3.0-r2`。
- 已核实远程基线：`LinzeColin/MetaDatabase` 分支 `codex/jobhuntbot-online-v020-deployment`，提交 `cf820c7a5841242a4727eb6c40c35079eb9bb152`，属于 v0.2.0。
- v0.3.0 完整 Candidate 源码在本 ZIP；远程尚无可核验 v0.3.0 提交。Delivery Agent 观察最新仓库后按既有治理规则落库。
- 默认岗位刷新周期严格固定为 **6 小时**；任何其他值都会被配置校验拒绝。
- `evidence/local/` 只证明冷启动源码 Candidate 的确定性测试、HTTP/DOM 契约、重启读回和任务包完整性；当前容器 Chromium 受管理员 URLBlocklist 阻断，未把本地浏览器 NOT_RUN 写成 PASS。真实生产 Playwright 仍是硬门。
- NitroSend 已从执行路径中移除，既不是依赖也不是阻断项；不得等待、安装或调用它。
- 邮件使用任意标准 SMTP。SMTP 暂未就绪时，先以 `ALLOW_REGISTRATION=false` 完成其余部署；不得因此停止源码适配、数据库、运行时、DeepSeek、岗位发现和运维接入。
- 当前本地执行环境可能无法访问外部岗位 API；真实来源、标准 SMTP、DeepSeek 和 HTTPS 必须在目标环境重跑。

## 冻结范围

- 邮箱注册、验证、登录、忘记密码和密码重置。
- 多账户、多用户，私人资料与全部业务动作按 `user_id` 隔离。
- 上传简历后自动形成资料草稿并启动岗位发现。
- 推荐 Feed 支持关键词、城市、岗位族、技能、来源、新鲜度、资格、相关性、机会潜力和状态筛选。
- 普通用户默认使用平台 DeepSeek Secret；用户看不到、填写不了、导出不了 API Key。
- DeepSeek 不得推翻工作权利、Sponsorship 等确定性硬规则；失败时基础流程继续。
- 不抓取未经授权的 SEEK、LinkedIn、Indeed；不绕过 CAPTCHA、Cloudflare、登录或 2FA；不自动最终提交申请。

## Codex 最后一公里

- 先备份，后迁移，再部署。
- Secret 只进入服务器 Secret 管理或权限为 `0600` 的部署配置；不展示值。
- 部署 PostgreSQL、Web、Scheduler、Worker。
- 真实验证任意标准 SMTP、两账户邮箱生命周期、平台 DeepSeek、外部岗位来源和 6 小时调度；NitroSend 不得进入方案。
- 执行 `deploy/acceptance.sh`；失败只修第一处断点，然后重跑完整验收。
- 只有根目录 `ACCEPTANCE_RESULT.json` 的 `core_verdict` 为 `PASS` 且无 P0/P1，才可报告生产完成。
- 完成 commit、push、部署身份、回滚目标和 status 登记。

## Owner 不需要做的事

Owner 不运行终端、不编辑配置、不判断日志。只有真实邮箱/域名/Secret 权限、费用、法律或不可逆事项缺失时，才提出一个最小封闭动作。
