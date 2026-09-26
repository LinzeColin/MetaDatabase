# JobHuntBot Online

全中文、多用户的候选人求职系统，线上地址 https://jobhunt.linzezhang.com 。首要用户是金融与法律求职者。

## 做什么

```text
邮箱注册验证 → 上传一份或多份简历 → 确认少量高影响事实（工作权利、担保、城市、年限、资质）
→ 每 6 小时自动聚合合法岗位源（Remotive / Arbeitnow / Jobicy / Adzuna / Greenhouse / Lever / Ashby）
→ 先判硬资格（职级、年限、CPA/CFA、律师准入、执业证书、工作权利、担保），再排序
→ 每个岗位自动选最合适的那份简历 → 下载只含本人事实的岗位定制 DOCX → 本人到官方页面投递并记录
```

DeepSeek 只做可选的材料复核；没有 Key 或额度用完时，核心流程按确定性规则照常完成。系统不保存第三方招聘平台账号，不自动提交申请。

## 怎么跑

本地（SQLite，虚拟环境放在项目目录外）：

```bash
python3 -m venv /tmp/venv-jobhunt && /tmp/venv-jobhunt/bin/pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-jobhunt/bin/python -m pytest -q
```

业务主链路的端到端测试是 `tests/test_business_e2e.py`：注册 → 两份简历 → Greenhouse/Lever 录制响应经真实适配器聚合 → 硬资格过滤 → 按岗位选中法律简历 → DeepSeek（mock）复核 → 导出 DOCX 并逐段核对内容 → 时间快进 6 小时后由调度函数再聚合出新岗位。CI：`.github/workflows/jobhunt-ci.yml`（全量 pytest + PostgreSQL 上生产模式启动 `/readyz` + scheduler/worker 启动检查）。

生产（VPS3，Docker Compose，接入 Coolify 的 Traefik `coolify` 网络，不是 Coolify 托管应用）：

| 服务 | 命令 | 作用 |
|---|---|---|
| `web` | `alembic upgrade head && uvicorn app.main:app` | 网站；Traefik 只把流量给 `/readyz` 通过的实例 |
| `scheduler` | `python -m app.scheduler` | 每 60 秒把 `next_discovery_at` 已到期的用户排进 `discovery_runs` |
| `worker` | `python -m app.worker` | 逐个处理排队任务；完成或失败后都把下一轮排在 6 小时后 |
| `postgres` | postgres:17.6 | 唯一业务数据库 |

三者都是 `restart: unless-stopped`，因此"每 6 小时聚合"只依赖这两个常驻容器在跑，没有 cron。部署入口 `deploy/deploy.sh`（先加密备份、跑迁移、热切换、失败自动回滚）；`deploy/backup.sh`、`restore.sh`、`rollback.sh`、`diagnose.sh` 分别是备份、恢复、回滚、诊断。

## 数据在哪

- 业务数据：VPS3 上的 Docker 卷 `jobhunt_postgres`（PostgreSQL）与 `jobhunt_uploads`（加密简历原件）。
- 备份：release 目录下 `runtime-data/backups/jobhunt-*.tar.gz.enc`（`deploy/backup.sh` 生成，口令在 `.env` 的 `BACKUP_ENCRYPTION_PASSPHRASE`）。
- 配置与密钥：release 目录下 `.env`、`secrets/postgres_password.txt`、`OWNER_LOGIN.txt`，只在服务器，不进 Git。
- 本仓只放源码与合成测试数据（`tests/fixtures/`）。

## 已知未解决

- **真实邮件生命周期从没在生产走通过**（注册 → 收信 → 点链接 → 登录）。2026-08-11 唯一一次受控尝试只发出 1 封后中止。Owner 可先用 `/owner-entry`（`OWNER_ENTRY_ENABLED=true` + `OWNER_ENTRY_PASSWORD`）绕过邮箱走核心链路。
- **冷路由首个请求偶发 502/503**（2026-08-11 实测 `/openapi.json`）。`docker-compose.yml` 已有常驻 `web-canary` 热备实例，是否已在线上启用需下面第 3 步核对。
- VPS3 上还有一个已退出的 v0.2 容器 `jobhuntbot-online-app-1`（目录 `/srv/linze/apps/jobhuntos-online`），不属于当前运行时，清理需 Owner 决定。

## Owner 上线核验清单

以下命令都在 **VPS3** 上、JobHuntBot 的 release 目录（含 `docker-compose.yml` 与 `.env` 的目录）里执行。找目录：`docker compose ls | grep -i jobhunt`，CONFIG FILES 那一列的目录就是。以下用 `$REL` 代表它。

1. **同步代码并部署**（`$SRC` 为合入后 MetaDatabase 检出里的 `JobHuntBotOnline/`；`P` 规则保护服务器私有文件不被删）：
   ```bash
   rsync -a --delete --filter='P .env*' --filter='P secrets/*.txt' --filter='P OWNER_LOGIN.txt' \
     --filter='P runtime-data/***' --filter='P evidence/target-*' --filter='P evidence/migration-result.json' \
     --filter='P ACCEPTANCE_RESULT.json' "$SRC/" "$REL/"
   cd "$REL" && deploy/deploy.sh
   ```
   `deploy.sh` 开头的发布前检查若报 `manifest inventory drift`，说明 release 目录里还有旧文件，按报错列出的路径删除后重跑。
2. **环境变量是否齐全**（只打印是否已设置，不打印值）：
   ```bash
   for k in APP_ENV BASE_URL DOMAIN DATABASE_URL SESSION_SECRET DATA_ENCRYPTION_KEY EMAIL_LOOKUP_SECRET \
     ADMIN_EMAIL ADMIN_PASSWORD BACKUP_ENCRYPTION_PASSPHRASE SMTP_HOST SMTP_USERNAME SMTP_PASSWORD SMTP_FROM \
     DEEPSEEK_API_KEY ADZUNA_APP_ID ADZUNA_APP_KEY GREENHOUSE_BOARDS LEVER_COMPANIES ASHBY_BOARDS; do
     v="$(grep -E "^$k=" .env | tail -1 | cut -d= -f2-)"; [ -n "$v" ] && [ "$v" != "''" ] && echo "已设置  $k" || echo "缺失    $k"; done
   grep -E '^(ALLOW_REGISTRATION|DISCOVERY_REFRESH_HOURS|ENABLE_REMOTIVE|ENABLE_ARBEITNOW|ENABLE_JOBICY|OWNER_ENTRY_ENABLED)=' .env
   ```
   前 10 项必须"已设置"；`ALLOW_REGISTRATION=true` 时 SMTP 四项必须齐全；`DISCOVERY_REFRESH_HOURS=6`。Adzuna/Greenhouse/Lever/Ashby 可选，但至少要有一个来源启用。
3. **容器都在跑**：`docker compose --profile canary ps` → `postgres`、`web`、`scheduler`、`worker` 为 running（`web-canary` 若在就说明冷启动热备已启用）。
4. **域名健康**（任意机器）：
   ```bash
   curl -fsS https://jobhunt.linzezhang.com/healthz   # 期望 status=ok；version 等于 .env 的 APP_VERSION（2026-08-11 线上还是 0.3.0）
   curl -fsS https://jobhunt.linzezhang.com/readyz    # 期望 {"status":"ready","refresh_hours":6}
   for i in 1 2 3 4 5; do curl -s -o /dev/null -w '%{http_code}\n' https://jobhunt.linzezhang.com/openapi.json; done  # 期望全是 200
   ```
5. **SMTP 能登录**（不发信）：
   ```bash
   docker compose exec -T web python -c "import os,smtplib; s=smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ.get('SMTP_PORT','587')), timeout=20); s.starttls(); s.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD']); print('SMTP 登录成功'); s.quit()"
   ```
6. **DeepSeek Key 可用**：`docker compose exec -T web python tools/deepseek_probe.py` → `"verdict": "PASS"`（会消耗 1 次极小请求）。
7. **岗位源能取到数据**：`docker compose exec -T web python tools/online_source_probe.py` → `successful_job_count` 大于 0，逐来源看 `status`。
8. **6 小时聚合真的在跑**（这是业务判据）：
   ```bash
   docker compose logs --since 13h scheduler | grep 'enqueued'
   docker compose logs --since 13h worker | grep 'completed discovery run'
   docker compose exec -T postgres psql -U jobhunt -d jobhunt -c \
     "select id,user_id,trigger,status,jobs_seen,jobs_new,recommendations_updated,completed_at,left(error_summary,120) from discovery_runs order by id desc limit 10;"
   docker compose exec -T postgres psql -U jobhunt -d jobhunt -c \
     "select user_id,discovery_enabled,last_discovery_at,next_discovery_at from candidate_profiles where discovery_enabled;"
   ```
   期望：每个启用用户每约 6 小时有一条 `trigger=scheduled`、`status=completed` 的记录，`next_discovery_at = last_discovery_at + 6h`。
9. **真人链路**：浏览器打开 https://jobhunt.linzezhang.com/owner-entry（或注册一个专用测试邮箱）→ 上传一份合成简历 → 确认资料 → 推荐页出现岗位 → 点一个合格岗位"生成申请包" → 下载 DOCX 并用 Word 打开，核对姓名、目标岗位、经历都来自上传的简历。6 小时后回到推荐页，确认有新刷新时间或新岗位。
