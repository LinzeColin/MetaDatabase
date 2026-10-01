# JobHuntBot Online

一句话：全中文、多用户的求职系统——上传简历，每 6 小时自动聚合合法公开岗位，先判硬资格再排序，为每个岗位选最合适的简历并生成只含本人事实的定制 DOCX；不自动投递、不保存第三方平台账号。规格见 [SPEC.md](./SPEC.md)。

## 线上地址与是否真在跑

- 地址：`https://jobhunt.linzezhang.com`（VPS-3，Docker Compose 接入 Traefik `coolify` 网络）。
- 健康检查：`/healthz`（期望 `status=ok`）与 `/readyz`（期望 `{"status":"ready","refresh_hours":6}`）。2026-09-30 实测：HEAD 请求两者都是 405（接口只接受 GET），GET 都是 200，`/healthz` 返回 `version 0.4.0`。
- 数据最迟多久该更新一次：**6 小时**（`DISCOVERY_REFRESH_HOURS=6`，配置层强制；`scheduler` 容器每 60 秒排队到期用户，`worker` 容器处理，成功或失败都把下一轮排在 6 小时后）。判据在库里：`discovery_runs` 每个启用用户约每 6 小时一条 `trigger=scheduled、status=completed`（查询语句见 `文档/归档/上线核验清单_2026-08.md` 第 8 步）。
- 没有自动的新鲜度告警端点：未核实。

## 数据放哪

VPS-3 的 Docker 卷 `jobhunt_postgres`（业务库）与 `jobhunt_uploads`（加密简历原件）；备份是 release 目录下 `runtime-data/backups/jobhunt-*.tar.gz.enc`（`deploy/backup.sh`）；配置与密钥只在服务器的 `.env` 与 `secrets/`，不进 Git。本仓只放源码和合成测试数据 `tests/fixtures/`。

## 怎么部署 / 回滚

- 部署：把合入后的 `JobHuntBotOnline/` 同步到服务器 release 目录（rsync 命令见归档清单第 1 步），再运行 `deploy/deploy.sh`（先加密备份、跑迁移、热切换、失败自动回滚）。没有拉取式自动部署：未核实。
- 回滚：`deploy/rollback.sh [镜像]`；不带参数用 `runtime-data/rollback-image.txt`。数据库不会被回退。
- 增删文件后必须 `python tools/verify_taskpack.py --write-manifest`，否则发布前检查报 `manifest inventory drift`。

## 需登录 / 需凭据而停掉的功能

- 邮箱注册与验证邮件：需 SMTP 凭据；缺凭据时 `ALLOW_REGISTRATION=false`。真实邮件链路从未在生产走通（2026-08-11 只试过一次），标「需凭据，已停」。Owner 入口 `/owner-entry` 需 `OWNER_ENTRY_ENABLED=true` + 口令，默认关闭。
- DeepSeek 材料复核：可选，需 Key；没有时核心流程按确定性规则照常运行。
- Adzuna 岗位源：需 `ADZUNA_APP_ID/KEY`；其余岗位源免 key。

## 本地测试

```bash
python3 -m venv /tmp/venv-jobhunt && /tmp/venv-jobhunt/bin/pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-jobhunt/bin/python -m pytest -q
python tools/verify_taskpack.py
```

业务主链路的端到端测试是 `tests/test_business_e2e.py`。CI：`.github/workflows/jobhunt-ci.yml`。运行规则与硬边界见 `AGENTS.md`。
