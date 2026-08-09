# Canonical Product & Release Contract

## 控制面

| 项目 | 值 |
|---|---|
| 产品 | JobHuntBot Online |
| 产品版本 | 0.2.0 |
| 任务包版本 | 0.2.0 |
| 数据 Schema | 3 |
| 当前范围 | 路径一：私有单用户线上求职决策、DeepSeek 增强与追踪 |
| 部署授权 | A3：在既有 OVH、域名、私有仓和对象备份范围内做可回滚部署 |
| 公开发布 | 否；只有 Owner 私有入口 |
| Candidate 状态 | 55 项确定性测试与 HTTP 黄金事务通过；目标 Docker、HTTPS、浏览器、真实 DeepSeek Key 与部署身份待 Delivery 验收 |

## L0 北极星不变量

| invariant_id | 不变量 | 业务 Oracle |
|---|---|---|
| `NS-CANDIDATE-01` | 产品只站在候选人一侧，不建设招聘 marketplace | 用户跨来源处理岗位，不依赖平台内岗位库存 |
| `TRUTH-01` | 高影响事实来源可追溯，不能由系统或模型猜测 | 工作权利、Sponsorship、经验、毕业年份和薪资回答来自 Owner 或明确为未知 |
| `SAFETY-01` | 不保存第三方招聘账号，不绕过验证，不自动最终提交 | 无第三方密码/Cookie 输入；提交在官方页面由用户执行 |
| `USABILITY-01` | 普通用户零技术门槛 | 只需网页登录、填表、上传、粘贴岗位和一次性粘贴 DeepSeek Key |
| `RUNTIME-01` | 运行不依赖 Mac、launchd、活动 Agent 或人工保活 | Linux 容器重启后服务和数据恢复 |
| `DATA-01` | 单用户私有，文件、候选人事实、API Key 和 AI 内容受保护 | 未登录不可访问；敏感字段加密；Key 不回显/导出；恢复包可重建状态 |
| `EVIDENCE-01` | Saved/Prepared/Applied 严格区分 | 只有明确提交证据才能标记 Applied |
| `AI-AUTHORITY-01` | DeepSeek 只增强，不拥有硬性资格裁决权 | AI suggested_action 与规则冲突时，以规则 recommendation/eligibility 为准 |
| `AI-PRIVACY-01` | Provider 只收到完成任务的最小脱敏内容 | 姓名、邮箱、电话、个人链接、Session、Key、原始文件字节不在请求正文 |
| `COST-01` | 核心链路不依赖模型额度 | Key 缺失、余额不足、限流或 Provider 故障时规则黄金事务仍可完成 |

## L1 当前发布范围

### 主要用户

Owner 本人，使用桌面或手机浏览器进行个人求职管理。

### 核心问题

岗位分散、资格条件易误判、简历/经历选择不一致、申请措辞成本高、投递状态缺证据、结果不能形成长期反馈。

### 主黄金事务

```text
Owner 打开真实 HTTPS 入口并登录
→ 用真实信息完成首次资料确认
→ 在认证设置页粘贴 DeepSeek Key 并完成官方连通验证
→ 上传一份真实简历
→ 粘贴授权查看的岗位链接或完整 JD
→ 透明规则给出资格/匹配判断
→ DeepSeek 在不改变规则裁决的前提下增强说明和草稿
→ 系统选择简历和 2–4 段真实经历并生成申请包
→ Owner 在雇主官方页面手动提交
→ 回到系统记录提交证据与下一动作
→ 刷新、重登、应用重启后仍能读回
→ 可创建加密恢复包并在隔离目录恢复
```

### 用户可见结果

- 一眼看清 `Apply / Review / Skip / Needs user`；
- 看见规则理由、风险、未知项和下一步；
- 看见 DeepSeek 增强状态、使用模式和非敏感用量；
- 看见推荐简历、经历和申请草稿；
- 明确知道申请包不等于已提交；
- Provider 失败时原规则结果和进度不丢失；
- 能下载 Owner 可读 JSON、创建加密恢复包，并看到长期同步真实状态。

### DeepSeek 固定外部边界

- Base URL：`https://api.deepseek.com`；
- Endpoint：`/chat/completions`；
- Fast：`deepseek-v4-flash` + thinking disabled；
- Precision：`deepseek-v4-pro` + thinking enabled + reasoning effort high；
- JSON mode；
- Key 通过认证网页、Secret file 或环境注入；不进入包、Git、日志或 canonical export；
- 规则结论始终优先；
- 用户可随时停用、删除数据库 Key，或由部署方撤销服务器 Secret。

### 当前非目标

- 公开注册、多用户、租户隔离和收费；
- 招聘方发布/搜索候选人；
- SEEK/LinkedIn/Indeed 等平台抓取；
- 第三方账号登录、Cookie、验证码、2FA；
- Browser extension、Autofill、Auto-apply；
- 自动点击最终提交；
- 邮件/日历自动连接；
- Embedding、向量数据库、自治多 Agent；
- 自动改写原始简历文件；
- 让 AI 判定法律资格或保证就业结果。

## Acceptance 边界

核心发布最低必须达到：

- 隔离环境 `U5 + E5`：规则黄金事务、模拟 AI 矩阵、刷新/重登、进程重启、备份与恢复；
- 目标生产技术黄金事务 `U5 + E5`：临时隔离账户通过真实 HTTPS 完成写入、刷新、应用容器重启读回与自动清理，同时核验容器/存储/健康状态；
- Owner 完成真实资料后，生产核心事务达到 `U4 + E4`；
- Owner 在网页粘贴 Key 并验证后，DeepSeek 增强达到 `READY`；
- 不得用模拟 Provider 响应冒充真实官方 API 通过。

Delivery Agent 不能在生产库虚构 Owner 签证、工作权利、Sponsorship、学历或经历，也不能要求 Owner 在聊天中发送 Key。

## Kill Criteria

出现以下任一且无法在当前边界修复时，不扩大自动化：

- 系统或模型擅自生成高影响事实；
- AI 覆盖硬性资格冲突；
- 直接身份信息、Key 或第三方凭证泄露到 Provider/日志/导出；
- 无法区分 Prepared 与 Applied；
- 绕过第三方登录或验证；
- Provider 失败导致核心规则、数据或进度不可用；
- 重启后数据丢失或恢复不可用；
- 同步状态错误显示为成功。

## 事实优先级

1. Owner 当前线程最新且明确授权；
2. 本文件 L0/L1 与 `acceptance_contract.json`；
3. 目标环境真实运行、数据和权限；
4. 目标仓适用治理与安全规则；
5. 当前源代码和执行测试；
6. DeepSeek 与依赖的官方文档；
7. 旧任务包、上游 JobHuntBot 工作流和 Agent 推断。
