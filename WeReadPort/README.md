# 阅迁｜微信读书与个人阅读资产账户平台

阅迁 v0.0.0.1.9 将原来的匿名迁移工具升级为账户中心化、多租户的个人阅读资产平台。首页提供用户注册、邮箱密码登录、微信读书密钥建账/登录，以及 Google、GitHub、Notion 登录；旧匿名迁移能力保留在 `/migrate/`，但不再代表当前产品主合同。

## 当前版本能力

- **统一账户**：不可变 `account_id` 是唯一身份主体；微信读书密钥、邮箱密码和 OAuth 身份只是可轮换、可显式绑定的凭据。系统不会因为邮箱相同自动合并账户。
- **密码与多平台登录**：支持用户注册和密码登录，以及 Google/Gmail、GitHub、Notion OAuth 登录或创建账户；支持登录后显式绑定平台身份。密钥或 OAuth 建账用户可在账户中心补设邮箱密码，并查看、撤销其他设备会话。
- **微信读书密钥**：支持密钥创建账户、登录、绑定与轮换。只保存不可逆指纹和账户级加密凭据，不把密钥写入 URL、日志、状态、行为事件或导出文件。若历史密文未能通过账户校验，界面会明确提示安全恢复；用户重新验证同一把已绑定密钥后，后台会强制完整重建可从来源重新取得的内容、逐条回读校验，并保留无法重建的历史项而不静默删除。
- **个人笔记长期存储**：OVH SQLite 保存账户索引、会话、游标、幂等、队列、Runtime Journal 与 Outbox；Cloudflare R2 保存账户级 AES-256-GCM 加密正文对象；Private-Database 只接收脱敏结构化完成态事实和对象引用；OCI 保存异地冷备。
- **四平台一键导入**：Google Drive、GitHub App、Notion 使用官方授权和最小权限完成“连接—选择—预览—确认—导入”；Obsidian 使用用户在本机选择的 Vault 文件夹、ZIP 或 Markdown/TXT，不伪造不存在的统一 Obsidian 登录。导入选择正文只以账户级加密暂存，任务结束立即清除。
- **小白流程**：首页直接展示三种登录路径；登录后提供三步向导和中文解释，不要求用户理解仓库、Vault、OAuth、JSON 或 API。移动端、320px、键盘、减少动态和高对比模式均有冻结检查。
- **跨设备同步**：服务端提供账户级增量游标、幂等键、乐观版本冲突和删除事件；并发修改不会静默覆盖。
- **画像与可视化**：在明确同意后，以确定性聚合生成阅读热度、来源分布、主题偏好、活跃趋势和可解释推荐；关闭同意后删除非必要行为事件；运行期不调用模型，Agent 与 Token 依赖均为零。
- **AI 问询**：搜索结果默认按书籍归档并可折叠；支持作者和时间归档。对选中的单条笔记，可选择 ChatGPT、Claude、DeepSeek、豆包或 Kimi，以及盲点反思等提问风格；浏览器先复制文本，再打开你选定的平台，不把笔记正文代为上传。个人补充信息与自定义提示词按账户加密保存。
- **单一公开入口**：生产仅开放 `weread.linzezhang.com`。不存在公开管理子域；账户和数据权限始终由同一受控服务端执行。
- **更广微信读书读取**：通过冻结的官方 gateway/Skill 合同先做能力发现，再有界分页读取书架、笔记本、划线、想法、个人书评、书籍信息、进度、章节、阅读统计、热门划线和推荐；不再限制 Top 5。全量同步先返回已入队任务，再由 OVH 工作器续租执行和前端轮询，避免把长任务卡在账户 HTTP 超时内。
- **账户权利**：支持查看和修改资料、导出账户数据、撤销平台连接、删除笔记与永久删除账户。高风险操作要求近期重新验证。
- **生产运行**：OVH Linux systemd 运行账户 API、导入工作器、健康、自愈、备份、事实同步和 R2→OCI 冷备；仅当账户服务不可达且数据库完整性正常时，健康单元才会清除 systemd failed 状态并有界重启 API 与工作器，同一故障五分钟内不会重复抖动；R2 等依赖退化只记录失败，数据库完整性异常绝不自动恢复数据。不使用 macOS launchd，不依赖开发 Agent 会话或后台模型。
- **多租户背压**：每个账户默认最多保留 6 个 PENDING/RUNNING 导入任务，额度由 SQLite 原子裁决，避免单一账户耗尽公共导入工作器；幂等重试仍返回原任务。

## 运行平面

```text
浏览器 / Cloudflare Worker
  ├─ 静态中文账户 UI、隐私、条款、状态和匿名兼容入口
  └─ 同源 Worker 薄代理（不持久化用户数据）
        └─ HTTPS → OVH 账户服务（Node.js 22 + systemd）
              ├─ SQLite：实时事务、索引、同步、队列、Outbox
              ├─ R2：加密笔记与用户对象
              ├─ Private-Database：脱敏结构化事实和恢复记录
              └─ OCI：R2/D1 异地冷备
```

自有 Cloudflare Worker 只绑定 `weread.linzezhang.com`，并配置 `WEREAD_ACCOUNT_SERVICE_URL=https://weread-api.linzezhang.com`、`WRP_INTERNAL_PROXY_SECRET`、`WRP_PUBLIC_HOST=weread.linzezhang.com` 与发布身份。OVH 账户服务始终只监听 `127.0.0.1:8788`；Coolify Traefik 只经 Docker 私网桥接到该端口，不能直接开放明文 HTTP 端口。

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

真实环境由 Owner 填写 `/etc/weread-port/platform.env` 中的 R2、OAuth、Private-Database 工作树、OCI 输入、`WRP_PUBLIC_BASE_URL=https://weread.linzezhang.com` 与边缘部署身份；`WRP_ADMIN_BASE_URL` 和 `WRP_ADMIN_ACCOUNT_IDS` 必须留空。预检不会回显 Secret，再执行安装：

```bash
sudo python3 service/scripts/platform_preflight.py --env-file /etc/weread-port/platform.env --require-paths --strict
sudo python3 service/install_platform.py --apply
```

启动、停止、诊断、备份、恢复、回滚、状态适配和生产 Smoke 的精确命令见正式任务包 `assets/OPERATIONS_RUNBOOK.md`。安装器采用版本化 release 和 `current` 软链接，失败时不得覆盖 Owner 的后续修改。

## 安全与真实性边界

- 任何曾在聊天、工单或日志出现的真实密钥一律视为泄露，不能进入代码、任务包、测试或部署配置，必须撤销并轮换后才能执行真实 E2E。
- 7×24 是架构、恢复、监控与运维目标，不是尚未发生的长期运行证明。
- `/healthz` 只证明公开入口存活；`/readyz` 主动验证 SQLite、R2 写读删、worker 心跳、OAuth 配置和业务依赖图，失败返回 503；`/api/status` 只发布脱敏状态，不读取用户正文或凭据。
- 生产 OAuth、R2、OVH、Private-Database、OCI 与 Cloudflare Worker 的真实可用性只能由目标环境证据裁决，不能由本地测试冒充。


## 冻结浏览器验收依赖

核心账户 UI 与生产账户链路不得跳过浏览器验收。执行环境安装：

```bash
python3 -m pip install --user -r requirements-production-e2e.txt
# Chromium 必须位于 /usr/bin/chromium 或 PATH；也可设置 CHROMIUM_PATH。
```
