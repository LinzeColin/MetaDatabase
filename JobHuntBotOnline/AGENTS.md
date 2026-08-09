# JobHuntBot Online Delivery Rules

本文件适用于当前包全部路径。目标仓存在更严格安全或部署规则时同时遵守；语义冲突按 `taskpack/CANONICAL_CONTRACT.md` 的事实优先级处理。

## 1. 事实与范围

- 产品版本：`0.2.0`。
- 任务包版本：`0.2.0`。
- 数据 Schema：`3`；部署自动迁移早期明文字段、旧上传对象名和新增 AI 表。
- 本包是完整可部署 Candidate，不是已经通过目标生产环境验收的声明。
- 保留路径一：Owner-only、无第三方招聘账号、无验证码绕过、无浏览器填表、无自动提交。
- DeepSeek 是已实现的可选增强层；透明规则引擎是核心业务裁决层。AI 不可推翻工作权利、Sponsorship、毕业年份、经验或其他硬性冲突。

## 2. Delivery Agent 责任

Delivery Agent 对目标环境端到端结果负责：观察、可逆适配、部署、运行、故障定位、修复、重测、回滚和真实入口验证。不得只报告“代码已上传”“容器已启动”“HTTP 200”或“模型已配置”。

先复现第一处断点，再做最小可逆修复。保护目标仓更新、更好的现有实现；不要用整包覆盖未理解的上游变化。任务分类只使用：`satisfied / apply / adapt / equivalent / conflict / blocked / obsolete`。

## 3. Owner Gate

只有以下事项需要 Owner 决策：

- 改变北极星、主要用户、黄金事务或当前范围；
- 新增公开注册、多租户、收费、第三方自动登录或自动提交；
- 改变长期数据权威；
- 新增未授权付费服务或超出既有成本上限；
- 公开发布、品牌/法律风险、不可逆删除；
- 无法从环境确定的真实域名冲突或权限缺失；
- DeepSeek API Key 本身由 Owner 在认证网页输入或由既有 Secret manager 注入，Delivery Agent不得索取明文。

普通端口、路径、代理、systemd、Docker、DNS、仓库目录、模型错误映射和兼容性修复由 Delivery Agent 自主处理。

## 4. Secret、隐私与模型数据

- 不把 `.env`、`OWNER_LOGIN.txt`、DeepSeek Key、Cookie、密码、OAuth、验证码、R2 凭证、私有简历或恢复包提交到 Git。
- 不在日志、Issue、截图、报告或聊天中展示完整 Secret。
- `.env` 权限保持 `0600`；运行数据目录仅部署用户和容器用户可访问。
- DeepSeek Key 优先来自 Secret file，其次服务器环境，最后是网页加密数据库；网页永不回显完整值。
- AI Provider 配置和 Key 不进入 canonical export、Owner 导出、Private-Database 或 R2 结构化同步。
- 发往 DeepSeek 的内容必须经过最小化和直接标识符脱敏；不得发送原始文件字节、姓名、邮箱、电话、个人链接、第三方账号、Session、恢复密钥或未授权私密备注。
- 生产候选人资料只能由 Owner 真实填写；测试只使用 `fixtures/` 中合成数据。

## 5. 代码与验证

- Python 变更必须通过语法解析和相关测试。
- UI/路由变更必须重新运行隔离浏览器黄金事务。
- AI 变更必须覆盖：成功、401、402、429、500/503、超时、预算上限、熔断、脱敏、密钥不回显、规则不被覆盖和降级可用。
- 部署/代理变更必须重新运行公网 HTTPS 的临时隔离账户完整写入、重启读回与自动清理验收。
- 数据/备份变更必须重新执行恢复包、重启读回和隔离恢复。
- 不降低 `taskpack/acceptance_contract.json`；不把未运行、阻断、配置缺失、模拟调用或旧结果写成真实 Provider PASS。

## 6. 部署与提交

- 在目标目录保留已有运行版本和数据恢复点。
- 使用 `deploy/generate_env.py` 创建生产配置；不得手工编造 Secret。
- 使用 `deploy/deploy.sh`，失败时确认自动代码回滚或执行 `deploy/rollback.sh`。
- 使用 `deploy/acceptance.sh` 完成冻结验收。
- 核心产品可在 DeepSeek 未配置时安全运行；但总 `PASS` 只有在 Owner 网页验证真实 Key 后成立。
- 验收通过后按目标仓既有规则提交。Owner 默认偏好直接更新 `main`，不新建长期 PR/分支；强制规则冲突时报告事实。
- 不自行改变版本号、模型名或数据 Schema。

## 7. 停止条件

- 核心 Acceptance 通过、无 P0/P1、真实入口可用：核心完成。
- DeepSeek 网页验证和已授权同步均 ready：完整发布完成。
- 只有 Owner-only 权限、域名、法律、数据权威或 Key 输入阻断时，继续完成其他工作后只提出一个最小封闭动作。
- 同一修复两次仍失败：回滚并定位根因，不循环试错或放宽 Acceptance。
