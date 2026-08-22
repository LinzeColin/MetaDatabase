# DSH Desktop 模型上下文一致性（2026-08-23）

## 结论

- DSH `llm-pi-ai` 的 `contextWindow` 是输入与输出合计的模型总窗口。压缩策略会据此计算阈值，不能先把预留量从配置值中扣掉。
- 内置 pi-ai 目录把 Kimi K3 定义为 `1,048,576`、K3-256K 定义为 `262,144`；DeepSeek V4 Flash/Pro 与 MiniMax M3 的已核目录为 `1,000,000`。
- 本机 SCNet 统一为：DeepSeek V4 Flash/Pro、Qwen3.8-Max、MiniMax-M3、GLM-5.2 均 `1,000,000`，Kimi-K3 为 `1,048,576`。DeepSeek 官方三项均为 `1,000,000`。
- `GLM-5.3` 当前账号真实调用返回 HTTP 403，不能因为 `/models` 可见就加入正常选择器。

## 本机验证与变更

- `settings.yaml` 已补齐 DeepSeek 官方 Flash/Pro，以及 SCNet Pro、Kimi K3、GLM-5.2；既有 Qwen 与 MiniMax 窗口已提升到真实总窗口。
- DSH settings-file 默认使用 chokidar 监听并保留最后一份有效文档；配置通过 YAML 解析及模型唯一性检查。
- 本轮检查时 DSH Desktop 没有运行，因此没有启动或重启它；下一次正常启动会直接读取新配置。
- 修改前保留了 `~/.dsh/settings.yaml.before-model-context-20260823-070754`；凭据、会话、皮肤、素材和外置图标均未修改。

## 长期规则

- Kimi 与 DSH 的容量映射统一读取 `desktop-suite/MODEL_CONTEXT_CONTRACT.json`；本机凭据继续留在外部配置和凭据存储中。
- `maxTokens` 是单次最大输出，不等于总上下文；本轮只修正总上下文，不用高输出上限制造额外成本或超时。
- 模型目录、账号授权、协议兼容三项必须分别验证；任何一项不成立都不进入正常可选菜单。
