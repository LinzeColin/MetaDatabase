# Cloudflare 双域名边缘策略

这是可静态核对的部署合同，不是 Cloudflare 控制台已经配置完成的声明。

| 入口 | 用途 | 身份边界 | Core 行为 |
|---|---|---|---|
| `social-archive.linzezhang.com` | 私人资料库/UI | 必须启用 Cloudflare Access；通过后由 Tunnel 注入 `Cf-Access-Jwt-Assertion` | 只在这个精确 `Host` 接受 Access 身份 |
| `social-archive-api.linzezhang.com` | Chrome 扩展 API | 不启用会触发交互跳转的 Access 登录 | 只认 Bearer Token（由已登录的资料库页面签发，可撤销）；不接受 Access Header 作为替代 |

- API 无令牌公开路径仅 `GET /health`。一次性配对码的三条路径（`/v1/pairing/status`、
  `/v1/pairing/exchange`、`/v1/pair`）已随 v0.0.0.7 / T03 删除——扩展改用由已登录页面
  签发的长期可撤销令牌，无需任何无令牌公开入口。其他业务路径由 Core fail-closed。
- API 域名上的 Cloudflare Rate Limit **保持不变**：真实规则为每 IP `1 次 / 10 秒`
  （持续上限不超过 6 次/分钟）。它原本是为保护一次性配对交换而设；那条路径已随
  v0.0.0.7 / T03 删除，但**规则不随之放宽**——现在它作为 API 域名的通用滥用防护继续生效。
  这是一条已在生产验收过的边缘规则，收紧或放宽都要重新走本文件的外部验收。
- 一次性码的 10 分钟有效期、5 次尝试上限、16 KiB 请求体上限已随配对链路一并移除，
  因为再没有对应的端点。取代它的长期令牌**不设过期**但可随时撤销：撤销后扩展上行立刻 401。
  WAF 仍应限制方法、请求体和异常 User-Agent。
- Tunnel origin 只绑定 loopback，不开放 OVH 公网端口。Core 不信任 `X-Forwarded-Host` 来放行 Access，只检查实际 `Host` 与 Assertion；该设计依赖 Tunnel/Access 先隔离公网来源。
- Core 的容器内端口仍是 `8765`，但 OVH 只暴露隔离的 `127.0.0.1:18765`；该端口由 `.env` 的 `SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT` 控制。它避免占用已有生产服务，Tunnel 的资料库与 API hostname 都只转发到它。
- `status.linzezhang.com` 是已有的全域状态站，不能被本产品接管根路径。`social-archive-status-web.service` 只能绑定 `127.0.0.1:18780`，只读取 `/var/lib/social-archive/status/social-archive.json`，只响应 `GET`/`HEAD`，绝不回写 Runtime、Outbox、内容、路径、凭据或 Provider 回包。Tunnel 先把精确的 `/social-archive.json` 与 `/social-archive-health` 路由到该隔离服务；同 hostname 的其余现有路径才透传至本机 Traefik `127.0.0.1:80`。因此公开的脱敏投影固定为 `/social-archive.json`，不以根路径冒充或覆盖既有状态站。systemd 定时器仅以只读方式读取部署目录的受限 API Token，向该投影文件写入脱敏文件。

## Owner 外部验收（本地不能代替）

在真实 OVH/Cloudflare 环境中，须分别记录下列结果；缺任何一项均不能把 SA-505 标为 PASS：

1. OVH 上 `core-api` 只有 `127.0.0.1:18765`，公网端口直连失败；
2. 两个产品 hostname 都路由到 loopback Core；`status.linzezhang.com/social-archive.json` 与 `/social-archive-health` 精确路由到隔离状态服务，默认 ingress 为 404；
3. 无 Access 会话访问 UI 被 Cloudflare Access 阻断；API Host 不发生交互式 Access 跳转；
4. API Host 上除 `GET /health` 外一律无 Bearer 即 401，且 UI 的 Access Header 不能放行 API Host；
   资料库页面登录后能签发扩展令牌，撤销后扩展上行立刻 401；
5. WAF/Rate Limit 的真实 Rule ID、Access Application ID、截图、时间和回滚记录，以及已脱敏的 status 响应、`status.linzezhang.com` 的有序 Tunnel route 与只读服务运行证据均完整。

真实 Rule ID、Access Application ID、Tunnel 凭据、截图和回滚记录写入受控 SA-505 Evidence，不写入源码、`.env.example` 或诊断包。`scripts/deployment_probe.py --read-only` 只报告 `NOT_RUN`；只有 Owner 明确执行 `--network-confirmed` 才会发出 DNS/HTTPS 探针。
