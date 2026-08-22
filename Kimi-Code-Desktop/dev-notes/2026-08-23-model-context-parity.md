# Kimi Code 模型上下文一致性（2026-08-23）

## 结论

- `max_context_size` 是模型输入与输出合计的总上下文窗口，不是扣除压缩预留后的可用量。
- Kimi K3 使用 `1,048,576`；独立的 `k3-256k` 档仍是 `262,144`。DeepSeek V4 与可用 SCNet 路由使用 `1,000,000`，SCNet Kimi K3 使用 `1,048,576`。
- 两个小写旧别名不能删除：`scnet/deepseek-v4-flash-0731` 在 45 个会话文件中有 13,352 条引用，`scnet/glm-5.2` 在 256 个会话文件中有 22,697 条引用。Kimi Code 恢复线程时按原 alias 再查当前配置，删除会让历史线程报“模型未配置”。
- 当前 Kimi 配置协议没有“只供恢复、从新任务选择器隐藏”的字段，因此先保留并明确标注旧任务兼容；不得用批量改写活动会话来伪装删除。

## 本机验证与变更

- DeepSeek 官方 Flash、Pro、Vision Exp 均真实返回 HTTP 200；SCNet Flash、Flash-0731、Pro、Kimi K3、Qwen3.8-Max、MiniMax-M3、GLM-5.2 均真实返回 HTTP 200。
- SCNet `GLM-5.3` 虽出现在 `/models`，当前账号真实请求仍返回 HTTP 403，因此没有加入可选配置。
- Kimi 官方直连凭据当前返回 HTTP 401；这是本机凭据状态，不是上下文字段问题。可用的 SCNet Kimi K3 不受影响。
- 运行中的 Kimi `GET /api/v1/models` 会重新读取 `config.toml`。更新后目录立即显示 14 项及新总窗口，GUI/backend PID 未变化，6 个 busy 会话保持运行。
- 修改前保留了 `~/.kimi-code/config.toml.before-model-context-20260823-070754`；文件权限仍为仅用户可读写。

## 长期规则

- 唯一源码契约是 `desktop-suite/MODEL_CONTEXT_CONTRACT.json`，三端契约校验会阻止额度和别名政策漂移。
- 供应商只返回模型名时，不能从“目录存在”推断上下文或账号权限；先核官方/运行库容量，再做真实最小调用。
- 不把 API key、账号可用性回执或本机会话写进发布包；软件更新也不覆盖外部配置。
