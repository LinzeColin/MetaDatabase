# 阅迁账户服务 v0.0.0.1.9

该目录是 OVH 上的账户、加密笔记、同步、导入、画像和微信读书广范围同步服务。运行时只依赖 Node.js 22 的内置模块、Linux systemd、SQLite、R2 S3 API 和已配置的 OAuth Provider。

## 关键命令

```bash
node service/server.mjs
node service/worker.mjs
python3 service/install_platform.py --root /tmp/wrp-check
python3 service/scripts/platform_preflight.py --env-file /etc/weread-port/platform.env --require-paths --strict
python3 service/scripts/platform_ops.py health
python3 service/scripts/platform_ops.py backup
python3 service/scripts/platform_ops.py restore-check /var/lib/weread-port/snapshots/<snapshot>.sqlite3
```

真实服务默认监听 `127.0.0.1:8788`。在 Coolify/Traefik 现网，`weread-port-edge-bridge.service` 只绑定 `WRP_EDGE_BRIDGE_HOST` 指定的 Docker 私网网桥，将请求转发至回环账户服务；`service/reverse-proxy/traefik.weread-origin.reference.yml` 是唯一允许的源站路由参考。公开 `origin.weread.linzezhang.com` 只供 Worker 连接，所有业务路径仍需要 Worker 内部 Secret；不得将账户服务或桥接绑定到 `0.0.0.0`。OVH 环境还必须将公开域固定为 `https://weread.linzezhang.com`、管理域固定为 `https://admin.weread.linzezhang.com`，并通过 `WRP_ADMIN_ACCOUNT_IDS` 配置至少一个不可变管理员账户 ID。

生产环境必须配置：

- R2 endpoint、bucket、access key；
- Google OIDC/Drive、GitHub App user authorization、Notion OAuth client；
- 会话 pepper、凭据 pepper、账户主密钥环和 Worker→OVH 内部共享 Secret；
- 公开域、专用管理域与管理员不可变账户白名单；
- Private-Database 已认证工作树；
- 可选 R2→OCI rclone remote。

不得把上述值提交到 Git、任务包、Sites 静态配置或日志。

## 生产正确性边界

- `/readyz` 会主动验证 SQLite、R2 写读删、导入 worker 心跳和 OAuth 配置；依赖不健康时返回 503，不能假绿。
- 微信读书全量同步通过同一受限工作器队列执行；`POST /v1/weread/sync` 只创建任务并返回 202，前端轮询任务状态，不以长时间 HTTP 等待伪装成“同步中”。
- 失败认证计数和锁定保存在 SQLite，服务重启不会绕过；导入选择正文使用账户级 AES-256-GCM 暂存，任务完成或失败即清除。
- 微信读书同步先返回可轮询的后台任务；实际广范围读取由同一受监控 worker 执行，避免长同步占满 Sites 到账户服务的响应窗口。
- 所有上游调用有有限超时与最多三次有界尝试；OAuth token 交换等非幂等请求不自动重试。
- GitHub 导入使用 GitHub App 用户令牌与用户选择的安装范围，不请求传统 `repo` 全量 scope。
