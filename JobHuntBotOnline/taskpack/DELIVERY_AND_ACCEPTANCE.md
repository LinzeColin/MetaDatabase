# Delivery, Verification, Release & Rollback

## 1. 任务 DAG

机器版见 `task_dag.json`。执行顺序：

| ID | 任务 | 依赖 | 关键输出 |
|---|---|---|---|
| `T01` | 观察目标仓、OVH、域名、代理、数据绑定和治理 | 无 | Current Truth + 第一断点 |
| `T02` | 放置 Candidate，保护现有实现，完成 C0/C1 适配 | T01 | 可构建源树 |
| `T03` | 生成生产配置、持久目录和 DNS/HTTPS | T02 | Secret 隔离、真实入口 |
| `T04` | 部署 App/Caddy 或接入现有代理 | T03 | 健康容器、迁移、回滚点 |
| `T05` | 执行规则黄金事务与 DeepSeek 故障/隐私矩阵 | T02 | 测试、HTTP、浏览器、恢复证据 |
| `T06` | 生产 HTTPS 完整事务、应用重启读回与临时账户清理 | T04,T05 | 真实写入、持久化和清理证据 |
| `T07` | Owner 在认证网页启用并验证 DeepSeek | T06 | Key 加密、官方 API ready |
| `T08` | 接入 Private-Database、R2、status | T04 | 诚实同步状态 |
| `T09` | 冻结证据、裁决、提交与交付 | T07,T08 | ACCEPTANCE_RESULT + URL |

`T07` 的唯一 Owner 动作是网页登录后粘贴一次 Key。Delivery Agent不得要求 Key 出现在聊天、Shell 历史、Git、任务包或报告中。若 Owner 尚未完成该动作，核心可以 `PASS`，总裁决只能是 `CONDITIONAL_PASS`。

## 2. 推荐执行

### 2.1 观察与落库

- 读取目标仓 `AGENTS.md`、部署规则和现有代理；
- 查找已有 JobHuntBot Online；不存在时默认 `LinzeColin/CodexProject/JobHuntBotOnline/`；
- 不新建仓库、公开 fork 或覆盖其他项目；
- 复制时排除缓存和临时证据；
- 运行 `python3 tools/validate_taskpack.py`。

### 2.2 生产配置

```bash
python3 deploy/generate_env.py \
  --domain REAL_DOMAIN \
  --admin-email OWNER_EMAIL
```

命令创建 `.env` 与 `OWNER_LOGIN.txt`，权限 `0600`，不得 commit。默认 `DEEPSEEK_API_KEY` 为空：这是刻意的安全设计，不是缺失实现。

若已有 Secret manager，可注入：

- `DEEPSEEK_API_KEY_FILE=/run/secrets/deepseek_api_key`（优先）；或
- `DEEPSEEK_API_KEY` 环境变量。

否则保持为空，让 Owner 在网页录入。任何路径都不能把 Key 写进仓库、命令输出或报告。

既有代理占用 80/443 时，保留 app 服务并接入现有代理，不启动第二个 Caddy 抢端口；仍满足 TLS、安全响应头和仅代理入口暴露。

### 2.3 部署

```bash
deploy/deploy.sh
```

脚本检查 Docker、加载配置、建立持久目录、将真实当前镜像保存为 `jobhuntos-online:previous`、为已有实例创建恢复点、构建/启动、迁移和核验敏感字段、执行容器 doctor、等待 ready；失败时回到前一应用镜像。

### 2.4 核心目标验收

```bash
deploy/acceptance.sh
```

目标主机执行：

1. 固定依赖和运行时一致性；
2. 55 项确定性测试；
3. 模拟 DeepSeek 成功、401、402、429、500/503、隐私脱敏和安全降级；
4. 真实 Uvicorn HTTP 黄金事务；
5. Playwright 独立浏览器事务；
6. 进程重启读回和加密恢复；
7. Compose、迁移、敏感存储和容器 doctor；
8. 公网 `/healthz`、`/readyz`、`/api/status`；
9. 创建临时隔离验收账户，在真实 HTTPS 完成 Onboarding、简历上传、岗位判断、申请包和进度写入；
10. 重启应用容器，重新登录并读回同一岗位状态和证据；
11. 删除临时账户、关联数据库记录和上传对象，再次核验敏感存储与健康状态；
12. `evidence/target-UTC/ACCEPTANCE_RESULT.json`。

服务器缺少 Playwright 依赖时，Delivery Agent安装目标 Chromium 依赖后重跑，不转交 Owner，也不把浏览器 Gate降为 HTTP。临时验收凭证只存在于权限为 `0600` 的短期文件和验收进程环境，不写入证据；无论成功失败都必须清理。

### 2.5 Owner 网页启用 DeepSeek

1. Owner 打开真实 URL并登录；
2. 进入“数据、AI 与安全”；
3. 在 DeepSeek 区域粘贴 Key；
4. 阅读“发送/不发送”边界并勾选同意；
5. 选择默认模式及每日预算；
6. 点击“保存并验证”。

成功后 `/api/status` 的 `deepseek.ready=true`。页面只显示末四位，不返回完整 Key。失败时显示可行动的错误，自动保持/切回规则模式。

## 3. 业务 Acceptance

### A-01 Owner 私有入口
未登录被引导登录；无公开注册；认证用户可进入受保护页面。目标环境使用临时隔离账户验证同一认证链路，不读取或泄露 Owner 密码。

### A-02 候选人事实
只收集必要高影响信息；yes/no/unknown 可表达；用户可修改；刷新/重启读回；系统和 AI 不补造事实。

### A-03 简历与经历
支持 PDF/DOCX/TXT/MD；超限/不支持文件拒绝；原文件和敏感字段加密；对象名不泄露文件名；经历可纠正。

### A-04 岗位导入
只读已审查公开 ATS；私网/回环拒绝；受限平台使用手工 JD；失败不丢输入；岗位下架后仍可读回快照。

### A-05 可解释规则
输出 recommendation、fit、eligibility、freshness、effort、reasons、risks、unknowns；硬性冲突不得 Apply；不使用伪概率；选择简历和最多四段经历。

### A-06 申请包与手动提交
显示材料、Why role/company、高影响答案和清单；草稿需用户核对；没有第三方登录/提交；Applied 必须有证据。

### A-07 进度与读回
阶段、下一动作、日期、证据和备注可记录；刷新、重登、进程重启以及生产应用容器重启后不变。

### A-08 数据与恢复
长期 JSON 私人字段加密；Owner 可下载可读副本；Provider Key 不导出；恢复包可在隔离目录重建；恶意路径/链接/超限恢复拒绝；同步状态诚实。

### A-09 Web 安全与运行
安全响应头、Cookie、CSRF、非 root 容器、只读根、私网 app、ready、生产 HTTPS 完整写入/重启读回、临时验收数据清理、前一镜像回滚和数据恢复可执行。

### A-10 零技术门槛
Owner 只收 URL、登录信息和网页内两个正常动作：真实资料确认、一次性 Key 粘贴。桌面和移动宽度均能完成核心路径；错误说明发生什么、下一步和数据状态。

### A-11 DeepSeek 安全 BYOK
Key 只在认证设置页/Secret manager进入；数据库加密；不回显、记录、导出或同步；可验证、停用和撤销；服务器 Secret 与网页 Key 的来源清楚可见但不泄露值。

### A-12 AI 隐私、预算与降级
请求前移除直接标识；固定官方 endpoint/model；JSON 输出受验证；每日预算、超时、有限重试和熔断有效；AI 不覆盖规则；Provider 故障保留规则、申请包和既有进度。

## 4. 裁决

- `PASS`：A-01 至 A-12 适用 Gate 在精确部署通过，DeepSeek 真实官方连通 ready，已授权长期同步 ready，无 P0/P1。
- `CONDITIONAL_PASS`：核心网页、安全、数据、回滚和规则黄金事务通过；仅 Owner 尚未网页启用 DeepSeek，或现有外部同步尚未授权。产品核心可使用，缺口必须明确。
- `FAIL`：业务、数据、权限、安全、Provider 边界、持久化或回滚违反 Oracle。
- `BLOCKED`：真实域名、生产权限或 Owner-only 治理决策缺失。

页面可打开、容器运行、模拟 Provider、测试通过或截图存在都不能单独证明完整 PASS。

## 5. 回滚与恢复

代码回滚：

```bash
deploy/rollback.sh
```

回到 `jobhuntos-online:previous`，保留当前业务数据。

数据恢复：

```bash
deploy/restore.sh runtime-data/backups/CHOSEN_FILE.jhbbackup
```

先恢复到空白暂存目录，通过解密、迁移、敏感存储、数据库和读回核验后切换；失败自动切回。

停止：

```bash
docker compose down
```

不加 `-v`，不删除 `runtime-data`。

## 6. 最终报告

```text
用户入口：REAL_HTTPS_URL
部署身份：仓路径 / commit / image / UTC
核心结果：PASS | FAIL | BLOCKED
总裁决：PASS | CONDITIONAL_PASS | FAIL | BLOCKED
DeepSeek：ready | configured_not_ready | not_configured（不得显示 Key）
结构化长期同步：synced | not_configured | failed
对象异地备份：synced | not_configured | failed
证据目录：target evidence path
第一处剩余断点：无或唯一事实
Owner 下一步：登录并完成真实资料/一次性 Key 输入（非技术动作）
```
