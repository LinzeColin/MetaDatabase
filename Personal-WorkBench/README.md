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

## 本地运行

```bash
cp .env.vps3.example .env.vps3
npm ci
npm run db:migrate:vps3
npm run dev
```

## VPS3 部署

- 镜像入口：`Dockerfile.vps3`
- Compose：`compose.vps3.yml`
- 数据库迁移：`npm run db:migrate:vps3`
- SQLite 历史数据导入：`npm run db:import-sqlite:vps3 -- /path/to/old.sqlite3`
- 数据库备份：`npm run db:backup:vps3`
- 数据库恢复：`npm run db:restore:vps3 -- /path/to/backup.dump`
- 生产验收：`npm run accept:vps3`

## 核心运行要求

- `DATABASE_URL` 必须指向 VPS3/Coolify PostgreSQL。
- `/data/objects` 必须挂载持久化卷。
- 邮箱、Google OAuth、Turnstile 和正式域名配置只通过生产环境变量注入。
- 任何发布必须在真实网址完成注册/登录、写入、刷新、重登、第二账户隔离和重新部署后读回。
