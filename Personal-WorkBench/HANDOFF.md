# Personal Workbench 当前交接

- 北极星：普通用户打开网站、注册或登录后即可使用个人工作台；数据保存到用户自己的云服务器与云数据库，并可跨设备继续使用。
- 生产入口：`https://mydairy.linzezhang.com`
- 源码：`LinzeColin/MetaDatabase/Personal-WorkBench`
- 计算节点：VPS3 / Coolify / Next.js Node.js
- 权威数据库：PostgreSQL
- 私有文件：VPS3 持久化对象目录
- 禁止依赖：ChatGPT Sites、ChatGPT Science、OpenAI Hosting、Cloudflare Workers、D1、R2 作为生产运行或权威数据面。
- 当前交付边界：代码、迁移、部署文件和验收程序已经进入最后一公里任务包；开发 Agent 只负责应用、提交、部署和真实环境回报。
- 最终通过条件：真实网址完成注册/登录、写入、刷新、重登、第二账户隔离、文件读回及重新部署后持久化。

## 2026-08-21 接管补正

- 继承基线：`fcba2feb`（VPS3 PostgreSQL 迁移任务包）；原接管 worktree 保持干净，后续修改位于独立 `_scratch` worktree。
- 已补正：新增 `.dockerignore`，使 `.env*`、私钥、数据库文件、依赖与构建输出不进入 `Dockerfile.vps3` 的 `COPY . .` 构建上下文；新增可提交的 `.env.vps3.example`；Compose 对 `APP_ORIGIN` 与 `POSTGRES_PASSWORD` 改为缺失即失败，并在 README 明确所有 Compose 命令须使用 `--env-file .env.vps3`。
- 本地结果：`docker compose --env-file .env.vps3 -f compose.vps3.yml config --quiet` 使用无密钥模板通过；`npm run check:release` 通过（现有 lint warning 6 条、无 error；核心测试 59 项、VPS3 运行时测试 8 项、Next.js production build 均通过）。
- 未声称完成：本机 Docker daemon 未运行，因此未实际构建或启动容器；未部署、未访问真实网址，也未执行账户、隔离、文件读回或重部署后的真实环境验收。
- 第三方验收入口：`docs/VPS3_PRODUCTION_ACCEPTANCE.md` 将七项条件映射为受真实账户、邮件验证和外部重部署回执约束的 Playwright 两阶段流程；fixture/公共 UI 测试不再被误作生产通过。
- 下一步：在获准的 VPS3/Coolify 环境填入真实变量并部署后，按该文档的预部署、独立重新部署、后部署三阶段逐项完成真实环境验收。
