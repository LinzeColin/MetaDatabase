# Codex 从这里开始

## 本包唯一目标

把当前目录作为 **JobHuntBot Online 0.2.0 的完整部署候选**，在 Owner 现有基础设施中完成最后一公里：重新观察真实环境、保护目标仓已有更优实现、完成可逆兼容适配、部署、执行冻结验收、修复真实断点、重新验收、接入现有长期同步与状态入口，并在核心 Gate 通过后提交落库。

本包已经包含产品代码、中文 UI、数据 Schema 3、透明规则引擎、DeepSeek 增强层、隐私处理、部署、迁移、备份、恢复、回滚和验收程序。不得重新进行产品研究、重写 PRD、改变产品方向或从零重构。

## 冻结范围

当前版本只实现路径一：

1. 单用户、Owner-only、私有 HTTPS 网页；
2. Owner 首次登录后填写真实求职边界；
3. 上传 PDF、DOCX、TXT 或 Markdown 简历；
4. 粘贴岗位链接；已审查的公开 ATS 可安全读取，其他页面保留链接并提示粘贴完整 JD；
5. 可解释规则先核验工作权利、Sponsorship、级别、地点、毕业年份、经验、技能、新鲜度和申请成本；
6. DeepSeek 在规则结论之上增强语义说明、材料聚焦和申请草稿，不能推翻硬性资格结论；
7. 选择简历和 2–4 段真实经历，生成申请准备包；
8. Owner 到官方雇主页面手动提交；
9. 回到系统记录真实成功证据、面试、拒绝或 Offer；
10. 数据刷新、重登、重启后可读回，并可创建加密恢复包。

禁止扩大到公开注册、多租户收费、招聘方后台、第三方账号登录、验证码处理、平台爬虫、浏览器 Autofill、自动投递或自动最终提交。

## DeepSeek 已内置的方式

代码、接口、模型路由、预算、错误降级和网页设置都已完成，不需要 Codex 再开发模型接入。

- 官方接口：`https://api.deepseek.com/chat/completions`
- 快速模式：`deepseek-v4-flash`，关闭 thinking，用于日常岗位增强；
- 精细模式：`deepseek-v4-pro`，启用 thinking，`reasoning_effort=high`，用于重要岗位；
- 输出：JSON object；
- 默认每日上限：60 次、600,000 tokens，可由 Owner 在网页降低或调整；
- 失败策略：401、402、429、500、503、超时和网络错误均不会破坏规则分析、原申请包或已记录进度；
- 密钥：不在 ZIP、Git、日志、长期导出或聊天中出现。

默认安全交付方式不是把密钥交给 Codex。部署完成后，Owner 登录网页，在 **“数据、AI 与安全 → DeepSeek 增强分析”** 中粘贴一次 API Key、确认数据边界并点击“保存并验证”。密钥加密保存，页面以后只显示末四位，可随时停用并删除网页保存的密钥。

若现有服务器已经使用 Secret file 或统一 Secret manager，Delivery Agent 可把 `DEEPSEEK_API_KEY_FILE` 或 `DEEPSEEK_API_KEY` 注入运行环境；不得要求 Owner 把密钥发到聊天、Issue、Git、截图或任务包。

## 第一动作

1. 阅读根目录 `AGENTS.md`。
2. 阅读 `taskpack/CANONICAL_CONTRACT.md`、`taskpack/DELIVERY_AND_ACCEPTANCE.md` 和 `taskpack/ARCHITECTURE.md`。
3. 观察目标仓/目录、OVH 节点、Docker、80/443、DNS、目标域名、现有代理、Private-Database 工作副本、R2/rclone、status 入口和目标仓治理文件。
4. 从 `taskpack/task_dag.json` 的 `T01` 开始，不跳过真实环境探针，不让 Owner 执行技术命令。

## 默认目标映射

- 代码仓：优先寻找现有 JobHuntBot Online；若不存在，默认放入 `LinzeColin/CodexProject/JobHuntBotOnline/`，未经授权不得新建仓库。
- 部署节点：Owner 现有 OVH Linux 节点。
- 默认域名候选：`jobhunt.linzezhang.com`；若已占用，使用同一根域的未占用子域并在最终报告中记录真实入口。
- 运行：Docker Compose + Caddy 自动 HTTPS，或接入现有反向代理。
- 事务数据：OVH 持久目录中的 SQLite。
- 结构化长期事实：现有 Private-Database；未授权时产品仍可运行，但必须显示 `not_configured`。
- 文件和恢复包：应用层加密；现有 R2/rclone 可用时接入异地备份。
- 本机依赖：零；不得使用 macOS、launchd 或活动 Agent 会话承载运行。

## Codex 可自主调整

允许 C0/C1 适配：端口、代理衔接、目录、Linux 权限、Compose 兼容、DNS provider、systemd timer、目标仓目录、状态页 Adapter、Private-Database/R2 薄接入和供应商兼容修复。

不得静默改变：产品范围、用户流程、数据权威、隐私边界、Owner-only 登录、人工最终提交、规则引擎的最终硬性裁决权、DeepSeek 官方接口/允许模型、Acceptance 或回滚终点。

## 完成标准

`deploy/acceptance.sh` 必须在目标环境生成 `ACCEPTANCE_RESULT.json`：

- `core_result=PASS`：真实 HTTPS、Owner 登录、核心黄金事务、安全、持久化、恢复和回滚通过；
- `verdict=PASS`：在核心通过基础上，DeepSeek 已通过真实官方 API 连通验证，且已授权的长期同步均为 ready/synced；
- `verdict=CONDITIONAL_PASS`：核心真实可用，但 Owner 尚未在网页粘贴 DeepSeek Key，或现有 Private-Database/R2 授权尚未提供；这些状态必须如实显示，不能伪装为完成；
- `FAIL/BLOCKED`：按验收契约保留真实断点，不降低 Oracle。

目标验收包括固定依赖、55 项确定性测试、模拟 DeepSeek 成功/失败/隐私矩阵、真实 Uvicorn HTTP 黄金事务、隔离浏览器事务、重启读回、备份恢复、迁移核验、公网 HTTPS、临时隔离账户完整生产写入、应用容器重启读回、自动清理和非敏感 DeepSeek 状态。

首次生产库不得填入虚构的工作权利、签证、身份或经历。Owner 登录后完成资料确认和一次性 DeepSeek Key 粘贴属于正常产品动作，不是技术配置。

## 最终只给 Owner

1. 可点击的真实 HTTPS 地址；
2. Owner 登录邮箱和一次性初始密码的安全交付方式；
3. 一句话操作：首次登录确认真实资料，在“数据、AI 与安全”粘贴 DeepSeek Key 并验证，然后上传简历、粘贴岗位；
4. `core_result`、总裁决、DeepSeek 非敏感状态、长期同步状态和唯一剩余 Owner Gate。

不要要求 Owner 打开终端、编辑 `.env`、理解 Docker/仓库、把 API Key 发给 Codex，或人工判断代码正确性。
