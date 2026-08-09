# JobHuntBot Online 0.2.0

一个私有、纯线上、候选人侧的 AI 求职操作系统。它不建设招聘 marketplace，也不替用户偷偷登录或海投；它把用户已经看到的岗位转化为一条可解释、可追踪、可恢复的求职决策链。

## 用户看到的流程

1. 打开私人 HTTPS 地址并登录；
2. 首次填写目标岗位、地点、工作权利、Sponsorship 和经验等高影响事实；
3. 在“数据、AI 与安全”粘贴一次 DeepSeek API Key并验证；
4. 上传简历，系统提取技能与真实经历；
5. 粘贴岗位链接；已审查 ATS 可安全读取，其他页面保留链接并提示粘贴完整 JD；
6. 先查看透明规则给出的 `Apply / Review / Skip / Needs user` 与理由；
7. 再查看 DeepSeek 对语义、材料重点和申请措辞的增强；
8. 查看推荐简历、2–4 段经历和申请问题草稿；
9. 在雇主官方页面自行提交；
10. 回来记录成功页面、申请编号、面试、拒绝或 Offer；
11. 刷新、退出重进或服务重启后继续查看同一状态。

普通用户不需要命令行、Docker、数据库、浏览器插件或本地常驻程序。DeepSeek 只需在认证网页粘贴一次 Key；不应把 Key 发给 ChatGPT、Codex、GitHub 或他人。

## 两层判断，而不是让模型随意决定

### 第一层：可解释规则

系统确定性核验：

- 目标/排除岗位；
- 级别与经验年数；
- 工作权利和 Sponsorship；
- Graduate cycle 与毕业年份；
- 地点和工作模式；
- JD 与简历技能交集；
- 发布时间和申请复杂度；
- 最合适的简历与经历组合。

硬性冲突不能被 AI 改成 Apply。系统只显示 `High / Medium / Stretch / Low` 与清楚理由，不把启发式包装成科学概率。

### 第二层：DeepSeek 增强

- 快速模式：`deepseek-v4-flash`，用于日常岗位；
- 精细模式：`deepseek-v4-pro`，用于重要岗位；
- 增强内容：中文语义说明、匹配/缺口、待确认问题、Why role/company 草稿；
- 预算：网页可设置每日调用和 Token 上限；
- 降级：余额不足、限流、超时或服务故障时，规则判断和已有数据继续可用。

## 安全与隐私

- 单用户 Owner 登录，没有公开注册；
- 不保存 SEEK、LinkedIn、Indeed 或 ATS 密码、Cookie、验证码；
- 不绕过 CAPTCHA、Cloudflare 或反机器人控制；
- 不自动点击最终提交；
- 不猜测工作权利、Sponsorship、薪资、身份和法律事实；
- 标记 `Applied` 必须记录成功页面、确认文字或申请编号；
- 原始简历、候选人资料、解析文本、经历库、申请答案、DeepSeek Key 与 AI 增强内容均使用应用级加密保存；
- Key 不回显、不进入日志、导出、备份清单或 Git；
- 发送给 DeepSeek 前移除姓名、邮箱、电话、个人链接和典型简历联系信息头；只发送完成当前岗位分析所需的最小文本；
- API 失效不会让核心产品停摆。

## 技术结构

- FastAPI 服务端渲染中文 UI；
- SQLite 单用户事务状态；
- 确定性规则引擎 + DeepSeek 官方 Chat Completions 增强层；
- 加密原文件、高敏字段、AI 配置/输出、长期 JSON 和恢复包；
- 复用目标机 Coolify Traefik 自动 HTTPS；
- Docker Compose 运行；
- Linux systemd timer 同步结构化事实和加密对象；
- 无 JavaScript 构建链、无外部前端 CDN、无本地 Agent 运行依赖。

架构与数据边界见 `taskpack/ARCHITECTURE.md`；生产依赖与官方 Provider 配置见 `taskpack/DEPENDENCIES.md`。

## 开发与本地验证

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
DATA_DIR=./runtime-data \
ADMIN_EMAIL=owner@example.invalid \
ADMIN_PASSWORD='Local-Only-Password-2026' \
SESSION_SECRET='local-session-secret-abcdefghijklmnopqrstuvwxyz' \
DATA_ENCRYPTION_KEY='v58zowyA7G8WmtqvK5SZbnwwQl76JJzhy1N9_Mi4uk4=' \
COOKIE_SECURE=false \
MAINTENANCE_ENABLED=false \
.venv/bin/python -m uvicorn app.main:app --reload
```

本地测试不需要真实 DeepSeek Key；`tests/test_ai_provider.py` 使用隔离 Mock Transport 核验请求、隐私、预算和故障降级。真实 Provider 连通只能由 Owner 在部署后的认证网页完成。

## 生产部署

目标 Linux 主机需具备 Docker Engine、Docker Compose、DNS 控制权和 80/443 入站。Delivery Agent执行：

```bash
python3 deploy/generate_env.py --domain jobhunt.linzezhang.com --admin-email OWNER_EMAIL
deploy/deploy.sh
deploy/acceptance.sh
```

真实 `.env`、`OWNER_LOGIN.txt` 和 DeepSeek Key 不得提交。Owner 只需在网页完成资料与 Key 录入。

## 备份与恢复

- UI 可生成 `.jhbbackup`；运行时也可按配置生成；
- 包含一致性 SQLite 副本、受保护结构化事实和加密上传；
- 恢复包整体再次加密；
- Owner 可下载本人可读 JSON；长期同步副本保持私人字段加密；
- Provider Key 和 Provider 配置不进入 canonical export；
- `deploy/restore.sh` 先在隔离暂存目录恢复并读回验证，再切换数据；
- `deploy/rollback.sh` 恢复前一应用镜像，不静默倒退业务数据。

## 许可证与来源

MIT。上游归属、非官方关系和第三方边界见 `LICENSE` 与 `NOTICE`。
