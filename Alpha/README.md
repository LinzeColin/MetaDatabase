# Alpha（7×24 自主交易 Agent 工作台，当前为影子盘）

一句话：按白盒规则用真实行情做模拟成交、记账、出报告的交易研究系统；当前运行模式是 **SHADOW（影子盘）**：不连券商、不动真钱，控制页永远不能下单。规格见 [SPEC.md](./SPEC.md)；30 秒了解现状读 `文档/00_我在哪.md`（七份文档由机器平面自动渲染，禁止手写）。

## 线上地址与是否真在跑

- 控制页：`https://alpha.linzezhang.com/`（标题「Alpha 驾驶舱」，页面每 30 秒自动刷新）。2026-09-30 实测 `curl -sI` 返回 405（该路径只接受 GET），GET 返回 200。
- 机器可读状态：`GET https://alpha.linzezhang.com/api/overview`（实测 200，含 `banner`、`mode_code`，2026-09-30 返回 `SHADOW`、「系统正常运行中」）；页面注明数据更新时间 `meta.updated_at_syd`。
- 数据最迟多久该更新一次：净值快照 **15 分钟**一次（`alpha-equity-snapshot.timer`：开机后 3 分钟起、每 15 分钟）；盘前自检周一到周五 UTC 13:15；账本备份每日 UTC 21:10；每日摘要 UTC 21:30（`deploy/vps3/systemd/`）。
- 域名到服务的路由配置不在本仓：未核实。

## 数据放哪

VPS-3：`/var/lib/alpha`（运行状态与账本）、`/opt/alpha`（代码检出、虚拟环境、环境文件）。本仓不放账户凭据、授权文件和运行数据（路牌见仓根 `WHERE_IS_PROJECT_DATA.md`）。

## 怎么部署 / 回滚

- 部署：在 VPS-3 以 root 运行 `Alpha/deploy/vps3/install.sh --repo <仓库地址> --sha <40 位提交号>`（幂等，提交号钉死，只写 `/opt/alpha`、`/var/lib/alpha`、`/etc/systemd/system/alpha*`）。退出码 0=完成并自检通过；2=环境文件里还有待填项，单元已装未启用。
- 回滚：用上一个已知良好的提交号重跑同一条命令；长驻服务（`alpha-trading-worker`、`alpha-notify-worker`、`alpha-supervisor`、`alpha-control-page`）出问题时 `systemctl stop` 即停新单（影子盘本就不碰券商）。

## 需登录 / 需凭据而停掉的功能

- 真实下单：需 Moomoo OpenD 登录与券商预签授权，已停；仓库默认 `DISABLED`，十一项门禁全过才可能开启，当前运行在 `ALPHA_MODE=SHADOW`。
- 邮件报告：需邮箱凭据（服务器环境文件，不入仓）；是否已配置：未核实。

## 本地测试

```bash
python -m pip install -e "Alpha[dev]"
cd Alpha && python -m pytest -q -p no:cacheprovider        # 2026-09-30 实测 438 passed, 1 skipped
python3 machine/tools/render_human.py && python3 machine/tools/check_doc_budget.py && python3 machine/tools/check_blocker_stop.py
```

CI：`.github/workflows/alpha-ci.yml`。运行规则与永久红线见 `AGENTS.md`；旧版 README、变更记录在 [文档/归档/](./文档/归档/)。本仓库公开：策略参数公开是 owner 知情决定，不构成任何投资建议。
