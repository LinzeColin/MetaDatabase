# 阅迁｜微信读书与个人阅读资产账户平台

阅迁 v0.0.0.1.8 将原来的匿名迁移工具升级为账户中心化、多租户的个人阅读资产平台。首页提供用户注册、邮箱密码登录、微信读书密钥建账/登录，以及 Google、GitHub、Notion 登录；旧匿名迁移能力保留在 `/migrate/`，但不再代表当前产品主合同。

## 当前版本能力

- **统一账户**：不可变 `account_id` 是唯一身份主体；微信读书密钥、邮箱密码和 OAuth 身份只是可轮换、可显式绑定的凭据。系统不会因为邮箱相同自动合并账户。
- **密码与多平台登录**：支持用户注册和密码登录，以及 Google/Gmail、GitHub、Notion OAuth 登录或创建账户；支持登录后显式绑定平台身份。密钥或 OAuth 建账用户可在账户中心补设邮箱密码，并查看、撤销其他设备会话。
- **微信读书密钥**：支持密钥创建账户、登录、绑定与轮换。只保存不可逆指纹和账户级加密凭据，不把密钥写入 URL、日志、状态、行为事件或导出文件。
- **个人笔记长期存储**：OVH SQLite 保存账户索引、会话、游标、幂等、队列、Runtime Journal 与 Outbox；Cloudflare R2 保存账户级 AES-256-GCM 加密正文对象；Private-Database 只接收脱敏结构化完成态事实和对象引用；OCI 保存异地冷备。
- **四平台一键导入**：Google Drive、GitHub App、Notion 使用官方授权和最小权限完成“连接—选择—预览—确认—导入”；Obsidian 使用用户在本机选择的 Vault 文件夹、ZIP 或 Markdown/TXT，不伪造不存在的统一 Obsidian 登录。导入选择正文只以账户级加密暂存，任务结束立即清除。
- **小白流程**：首页直接展示三种登录路径；登录后提供三步向导和中文解释，不要求用户理解仓库、Vault、OAuth、JSON 或 API。移动端、320px、键盘、减少动态和高对比模式均有冻结检查。
- **跨设备同步**：服务端提供账户级增量游标、幂等键、乐观版本冲突和删除事件；并发修改不会静默覆盖。
- **画像与可视化**：在明确同意后，以确定性聚合生成阅读热度、来源分布、主题偏好、活跃趋势和可解释推荐；关闭同意后删除非必要行为事件；运行期不调用模型，Agent 与 Token 依赖均为零。
- **更广微信读书读取**：通过冻结的官方 gateway/Skill 合同先做能力发现，再有界分页读取书架、笔记本、划线、想法、个人书评、书籍信息、进度、章节、阅读统计、热门划线和推荐；不再限制 Top 5。
- **账户权利**：支持查看和修改资料、导出账户数据、撤销平台连接、删除笔记与永久删除账户。高风险操作要求近期重新验证。
- **生产运行**：OVH Linux systemd 运行账户 API、导入工作器、健康、自愈、备份、事实同步和 R2→OCI 冷备；不使用 macOS launchd，不依赖开发 Agent 会话或后台模型。

## 运行平面

```text
浏览器 / ChatGPT Sites
  ├─ 静态中文账户 UI、隐私、条款、状态和匿名兼容入口
  └─ 同源 Worker 薄代理（不持久化用户数据）
        └─ HTTPS → OVH 账户服务（Node.js 22 + systemd）
              ├─ SQLite：实时事务、索引、同步、队列、Outbox
              ├─ R2：加密笔记与用户对象
              ├─ Private-Database：脱敏结构化事实和恢复记录
              └─ OCI：R2/D1 异地冷备
```

ChatGPT Sites 必须配置 `WEREAD_ACCOUNT_SERVICE_URL` 与 `WRP_INTERNAL_PROXY_SECRET`。OVH 账户服务默认只监听 `127.0.0.1:8788`，必须由现有 HTTPS 反向代理或 Cloudflare Tunnel 暴露；不得直接开放明文 HTTP 端口。

## 本地冻结验证

要求 Node.js 22.13+、Python 3.11+：

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm run verify:all
npm run build
```

不安装第三方依赖时仍可运行核心、账户、运维、静态页面和安全验证：

```bash
npm run verify:integration
```

## OVH 安装与回滚

先在隔离目录验证安装布局：

```bash
python3 service/install_platform.py --root /tmp/weread-port-install-check
```

真实环境由 Owner 填写 `/etc/weread-port/platform.env` 中的 R2、OAuth、Private-Database 工作树和可选 OCI 输入；Codex先运行不会回显 Secret 的确定性预检，再执行安装：

```bash
sudo python3 service/scripts/platform_preflight.py --env-file /etc/weread-port/platform.env --require-paths --strict
sudo python3 service/install_platform.py --apply
```

启动、停止、诊断、备份、恢复、回滚、状态适配和生产 Smoke 的精确命令见正式任务包 `assets/OPERATIONS_RUNBOOK.md`。安装器采用版本化 release 和 `current` 软链接，失败时不得覆盖 Owner 的后续修改。

## 安全与真实性边界

- 任何曾在聊天、工单或日志出现的真实密钥一律视为泄露，不能进入代码、任务包、测试或部署配置，必须撤销并轮换后才能执行真实 E2E。
- 7×24 是架构、恢复、监控与运维目标，不是尚未发生的长期运行证明。
- `/healthz` 只证明公开入口存活；`/readyz` 主动验证 SQLite、R2 写读删、worker 心跳、OAuth 配置和业务依赖图，失败返回 503；`/api/status` 只发布脱敏状态，不读取用户正文或凭据。
- 生产 OAuth、R2、OVH、Private-Database、OCI 与 ChatGPT Sites 的真实可用性只能由目标环境证据裁决，不能由本地测试冒充。
