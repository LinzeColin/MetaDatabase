# 生产依赖、DeepSeek 接口与升级边界

访问日期：2026-08-09。

核心规则不依赖外部模型；DeepSeek 是 Owner 自愿启用的增强服务。生产安装使用 `requirements.txt` 的精确直接版本；目标验收核对版本、依赖一致性和真实功能。

| 依赖 | 固定版本 | 用途 | 许可证 | 权威来源 |
|---|---:|---|---|---|
| FastAPI | 0.141.1 | Web 路由与表单 | MIT | https://pypi.org/project/fastapi/0.141.1/ |
| Starlette | 1.3.1 | ASGI、Session、静态文件与测试 | BSD-3-Clause | https://pypi.org/project/starlette/1.3.1/ |
| Uvicorn | 0.51.0 | ASGI 进程 | BSD-3-Clause | https://pypi.org/project/uvicorn/0.51.0/ |
| SQLAlchemy | 2.0.51 | SQLite 事务 | MIT | https://pypi.org/project/SQLAlchemy/2.0.51/ |
| Jinja2 | 3.1.6 | 服务端中文模板 | BSD-3-Clause | https://pypi.org/project/Jinja2/3.1.6/ |
| python-multipart | 0.0.32 | 表单和上传 | Apache-2.0 | https://pypi.org/project/python-multipart/0.0.32/ |
| HTTPX | 0.28.1 | 受限岗位读取、DeepSeek HTTPS 客户端、测试 | BSD-3-Clause | https://pypi.org/project/httpx/0.28.1/ |
| Beautiful Soup | 4.15.0 | HTML 正文提取 | MIT | https://pypi.org/project/beautifulsoup4/4.15.0/ |
| pypdf | 6.14.2 | PDF 文本读取 | BSD-3-Clause | https://pypi.org/project/pypdf/6.14.2/ |
| python-docx | 1.2.0 | DOCX 文本读取 | MIT | https://pypi.org/project/python-docx/1.2.0/ |
| argon2-cffi | 25.1.0 | Owner 密码 | MIT | https://pypi.org/project/argon2-cffi/25.1.0/ |
| cryptography | 50.0.0 | 文件、字段、Key 与恢复包加密 | Apache-2.0 OR BSD-3-Clause | https://pypi.org/project/cryptography/50.0.0/ |
| ItsDangerous | 2.2.0 | Session 签名 | BSD-3-Clause | https://pypi.org/project/itsdangerous/2.2.0/ |
| Python Official Image | 3.13.14-slim-trixie | 容器运行时 | 各组件许可证 | https://hub.docker.com/_/python |
| Existing Coolify Traefik | target-managed | HTTPS ingress | MIT | target host `coolify-proxy` |

## DeepSeek 官方接口锁定

| 项目 | 当前配置 |
|---|---|
| OpenAI-compatible Base URL | `https://api.deepseek.com` |
| Endpoint | `/chat/completions` |
| Fast model | `deepseek-v4-flash` |
| Precision model | `deepseek-v4-pro` |
| Fast thinking | disabled |
| Precision thinking | enabled |
| Precision reasoning effort | high |
| Response format | JSON object |
| Authentication | Bearer API Key |

官方文档：

- https://api-docs.deepseek.com/
- https://api-docs.deepseek.com/api/create-chat-completion
- https://api-docs.deepseek.com/guides/thinking_mode
- https://api-docs.deepseek.com/quick_start/error_codes
- https://api-docs.deepseek.com/quick_start/pricing
- https://api-docs.deepseek.com/updates

截至访问日期，V4 Flash/Pro 为官方模型；旧 `deepseek-chat` 与 `deepseek-reasoner` 已在 2026-07-24 到达停用日期，因此本包不使用旧名称。Provider 价格和限制可能变化，运行时由 Owner 在官方平台查看；产品使用 Token 预算而不是把价格常量写死。

## 安全版本选择

- Starlette 1.3.1、python-multipart 0.0.32、pypdf 6.14.2、cryptography 50.0.0 采用当前修复版本；
- 生产拒绝未审查的 DeepSeek Base URL 或任意模型别名；
- Provider 返回正文不直接进入日志；错误只映射为稳定内部代码和用户可行动提示；
- thinking 模式不发送无效采样参数；
- JSON mode 同时在 Prompt 中明确要求 JSON，避免空白输出。

## Preparation 证据边界

当前环境已执行源码、55 项测试、模拟 Provider 请求/错误/隐私矩阵、HTTP 黄金事务、重启读回和恢复。没有使用 Owner 的真实 Key，也没有声称真实 DeepSeek 账户、余额或网络已经通过。真实 Provider 验证必须在目标 HTTPS 网页由 Owner 完成。

当前环境没有 Docker daemon和可用的独立 Playwright Chromium，因此目标容器、Traefik 公网 TLS和浏览器事务由 `deploy/acceptance.sh` 强制执行。

## 升级规则

依赖或模型升级属于 C1/C2：只有官方变化明确、完整规则/AI/浏览器/恢复事务通过、数据格式不被静默改变、成本和隐私边界不扩大且可回滚时采用。不得在生产用无版本约束更新，也不得自动切换到未知模型或第三方代理端点。
