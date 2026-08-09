# Preparation Environment Acceptance Record

## 精确边界

以下结果证明 JobHuntBot Online 0.2.0 在当前 Preparation 环境中的源码、规则事务、DeepSeek 请求契约和本地进程行为。它不代表目标 OVH、DNS、TLS、Docker、真实 Owner Key、Private-Database、R2 或目标浏览器已经通过。目标部署必须重新执行 `deploy/acceptance.sh`。

## 已执行并通过

- Python 语法、导入路径、任务 DAG、Acceptance 引用和 Shell 语法检查；
- 55 项确定性测试全部 PASS；
- 其中 12 项 DeepSeek 专项覆盖：
  - 网页 Key 加密、末四位展示和不回显；
  - 更换 Key 后旧验证状态自动失效，必须重新连通验证；
  - 官方 `https://api.deepseek.com/chat/completions`；
  - `deepseek-v4-flash` 非思考快速模式；
  - `deepseek-v4-pro` 思考模式与 `reasoning_effort=high`；
  - JSON mode；
  - 姓名、邮箱、电话和个人 URL 脱敏；
  - AI 不覆盖规则引擎资格结论；
  - 401、402、429、500、503 错误映射；
  - 请求预算停止、有限重试、熔断和规则降级；
  - Provider Key 不进入请求正文、网页回显或长期导出；
- 真实 Uvicorn 子进程启动与 HTTP 黄金事务 PASS；
- 登录、首次资料、简历上传/解析/加密 PASS；
- 导入 JD、透明规则分析、生成申请包 PASS；
- Applied 提交证据、进程停止重启读回 PASS；
- 加密恢复包创建与恢复闭包 PASS；
- SQLite 高敏字段、随机上传对象名、字段加密 canonical export 和 Owner 可读下载边界 PASS；
- 生产配置生成、DeepSeek 空 Key 安全默认、Secret 文件权限 PASS；
- 密码修改使旧 Session 失效；ready 同时核验数据库和持久目录；
- 发布候选 ZIP 已在全新目录冷解压，并重新通过同一 55 项测试、12 项 DeepSeek 专项、HTTP 黄金事务、任务包验证、Shell 语法、执行权限和禁入文件检查；精确最终 ZIP 在封包后还会再执行一次相同验证。

机器结果：

- `evidence/local-acceptance-result.json`
- `evidence/http-golden-result.json`
- `evidence/ai-provider-local-result.json`
- `evidence/ai-provider-pytest.txt`
- `evidence/cold-extraction-result.json`

## DeepSeek 真实证据边界

当前环境没有使用 Owner 的真实 API Key，也没有向 DeepSeek 官方服务发起真实计费请求。Provider 请求与响应通过 HTTPX Mock Transport 进行协议级验证，因此只能证明：

- 代码会使用冻结的官方 endpoint、模型和参数；
- 发出前会执行数据最小化和脱敏；
- 成功、错误、预算和降级逻辑符合当前 Acceptance；
- 不证明 Owner Key、账户余额、网络出口或 DeepSeek 实际服务当前可用。

真实 Provider `READY` 只能由 Owner 在目标 HTTPS 设置页粘贴 Key 并完成官方连接验证后成立。模拟结果不得冒充真实 Provider PASS。

## 当前环境未能执行

- 系统 Chromium 受管理员策略限制，访问本地测试 URL 返回 `ERR_BLOCKED_BY_ADMINISTRATOR`；没有绕过该策略，也没有把浏览器流程写成 PASS。完整脚本在 `tests/e2e_golden.py`，目标环境必须使用专用 Playwright Chromium。
- 当前环境没有 Docker daemon，因此没有声称 Compose、Caddy、公网 HTTPS、容器固定依赖或真实回滚已经通过。
- Private-Database、R2 与 status 需要目标环境的现有授权和真实绑定。

## 当前最高证据

- 源码、规则事务、AI 合同和本地进程：`U5 / E5`；
- DeepSeek 真实官方连接：`NOT_RUN / OWNER_KEY_REQUIRED_IN_WEB_UI`；
- 浏览器 UX：`NOT_RUN / TARGET_DEDICATED_BROWSER_REQUIRED`；
- 目标生产部署：`NOT_RUN / DELIVERY_REQUIRED`；
- 7×24 长期运行：`OPERATIONAL_PROOF_PENDING`。

只有精确目标部署上的 `ACCEPTANCE_RESULT.json` 才能发布生产裁决。
