# 个人工作台 / Personal Workbench

普通用户打开网站、注册或登录后，即可直接使用个人工作台；所有数据保存到用户自己的云服务器与云数据库，并可在任意设备继续使用。

## 当前生产架构

```text
浏览器
  → mydairy.linzezhang.com
  → VPS3 / Coolify / Traefik
  → Next.js Node.js 应用
  → PostgreSQL 权威数据库
  → VPS3 持久化对象目录
```

生产运行不依赖 ChatGPT Sites、ChatGPT Science、OpenAI Hosting、Cloudflare Workers、D1 或 R2。Cloudflare 只可作为 DNS、代理、TLS 和 Turnstile 的外围能力。

## 源码本地检查

```bash
npm ci
npm run check:vps3
```

## VPS3 部署

- 镜像入口：`Dockerfile.vps3`
- Compose：`compose.vps3.yml`
- 先复制 `cp .env.vps3.example .env.vps3`，替换模板中的所有占位值；该私有文件不得提交。
- 每次 Compose 操作都必须显式载入该文件，先运行：

  ```bash
  docker compose --env-file .env.vps3 -f compose.vps3.yml config --quiet
  docker compose --env-file .env.vps3 -f compose.vps3.yml up -d --build
  ```

- Coolify 部署时，将模板中的同名变量配置在 Coolify 环境变量界面；不要把 `.env.vps3` 上传到仓库或镜像构建上下文。
- 容器入口会在启动 Next.js 前自动执行数据库迁移；`npm run db:migrate:vps3` 只应在已配置 `DATABASE_URL` 的目标运行环境中单独使用。
- SQLite 历史数据导入：`npm run db:import-sqlite:vps3 -- /path/to/old.sqlite3`
- 数据库备份：`npm run db:backup:vps3`
- 数据库恢复：`npm run db:restore:vps3 -- /path/to/backup.dump`
- 生产验收：`npm run accept:vps3`

## 核心运行要求

- `DATABASE_URL` 必须指向 VPS3/Coolify PostgreSQL。
- `/data/objects` 必须挂载持久化卷。
- 邮箱、Google OAuth、Turnstile 和正式域名配置只通过生产环境变量注入。
- 任何发布必须在真实网址完成注册/登录、写入、刷新、重登、第二账户隔离和重新部署后读回。
