# Canonical Contract｜JobHuntBot Online v0.3.0 SaaS

## 1. 版本与精确对象

| 项目 | 值 |
|---|---|
| Product | JobHuntBot Online |
| Product version | 0.3.0 |
| Taskpack version | 0.3.0-r1 |
| Schema baseline | Alembic `0001_saas_baseline` |
| Target repository | `LinzeColin/MetaDatabase` |
| Observed remote baseline | branch `codex/jobhuntbot-online-v020-deployment`, commit `cf820c7a5841242a4727eb6c40c35079eb9bb152` |
| Deployment target | Owner 现有 OVH/Coolify + HTTPS 域名 |
| Current authority | 本文件 + `acceptance_contract.json` + Owner 当前明确要求 |

远程基线属于 v0.2.0；v0.3.0 Candidate 随本任务包交付。Delivery Agent 必须先观察最新仓库，不能假设远程仍停在上述提交。

## 2. L0 不变量

- `INV-REAL-001`：真实用户必须完成核心事务，不能用代码、页面或容器声明代替可用。
- `INV-ZERO-TECH-002`：普通用户只操作网页，不接触命令、配置、数据库或 Secret。
- `INV-TENANT-003`：每个账户的简历、资料、推荐、申请包和历史严格隔离。
- `INV-TRUTH-004`：系统不猜测工作权利、Sponsorship、经历、学历、薪资或身份事实。
- `INV-AI-005`：普通用户默认使用平台 DeepSeek；Key 不向用户暴露，AI 失败不阻断核心规则链。
- `INV-REFRESH-006`：启用岗位发现后，下一轮刷新严格安排在本轮完成后的 6 小时。
- `INV-PLATFORM-007`：不绕过第三方平台限制，不自动最终提交申请。
- `INV-RECOVERY-008`：发布前可备份，失败可回滚；迁移后可读回和恢复。
- `INV-EVIDENCE-009`：未运行、阻断和未知不得写成 PASS。

## 3. 当前版本范围

### 用户可见

- 邮箱注册、验证、登录、退出、重发验证邮件、忘记密码和一次性密码重置；
- 上传简历优先的 Onboarding；系统自动提取技能和经历；
- 一页集中确认工作权利、Sponsorship、地点、工作模式、入职时间和排除项；
- 自动岗位发现与每 6 小时刷新；
- 推荐 Feed、来源状态、资格/相关性/机会潜力解释；
- 关键词、城市、岗位族、技能、来源、新鲜度、资格、相关性、机会潜力和用户状态筛选；
- 保存、忽略、准备申请、手工岗位导入、申请包和申请结果记录；
- 个人资料修改、数据导出、密码修改和账户删除；
- 管理员用户状态、用户 AI 额度和平台状态管理。

### 运行能力

- PostgreSQL + Alembic；
- Web、Scheduler、Worker 分离；
- 平台 DeepSeek Gateway、用户/平台预算和熔断；
- 加密候选人字段和上传对象；
- 备份、验证、恢复和应用镜像回滚；
- 生产验收结果 `ACCEPTANCE_RESULT.json`。

## 4. 非目标

- 招聘方发布后台或双边招聘 Marketplace；
- 未经许可抓取 SEEK、LinkedIn、Indeed；
- CAPTCHA、Cloudflare、2FA 绕过；
- 第三方招聘账号密码/Cookie 托管；
- 自动最终提交申请；
- 伪精确录用概率；
- 本版本收费、公开营销或企业多组织权限。

## 5. 黄金事务

```text
新用户打开真实 HTTPS
→ 邮箱注册并收到验证邮件
→ 完成验证并上传一份简历
→ 系统生成候选人草稿
→ 用户集中确认高影响事实
→ 系统自动发现岗位并形成推荐 Feed
→ 用户按城市/岗位/技能/关键词筛选
→ 打开岗位查看三层结论与官方入口
→ 保存或生成申请包
→ 手动在官方页面申请并记录真实结果
→ 刷新、重登、应用重启后仍可读回
```

第二账户不得读取第一账户的任何私有资源。

## 6. 生产完成标准

只有同时满足以下条件才可报告生产完成：

1. `deploy/acceptance.sh` 生成根目录 `ACCEPTANCE_RESULT.json`；
2. `core_verdict=PASS`；
3. 真实 HTTPS、SMTP、DeepSeek、PostgreSQL、Scheduler、Worker 均有本轮证据；
4. 两个独立测试账户完成正向事务与跨租户负向事务；
5. 应用重启后读回成功；
6. 备份可读且恢复步骤在隔离范围验证；
7. 无未关闭 P0/P1；
8. commit、部署身份和回滚目标已记录。

## 7. Owner Gate

只有域名/邮箱/Secret 权限、成本增加、数据权威变化、公开发布、法律或不可逆操作可以阻断并询问 Owner。普通技术适配由 Delivery Agent 自主决定。

## 8. 冲突优先级

1. Owner 当前线程最新明确要求；
2. 本 Canonical Contract 与 Acceptance；
3. 目标仓适用安全、部署和贡献规则；
4. 当前真实仓库、环境、数据与权限；
5. 官方文档和锁定第三方来源；
6. 旧任务包、旧分支说明和 Agent 推断。
