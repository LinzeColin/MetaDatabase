# ADP 历史包公开披露记录

## Owner 决定

Owner 于 2026-07-20 明确选择把本批 ADP 历史任务包与验收包归档到公开仓库 `LinzeColin/MetaDatabase` 的 `arxiv-daily-push/docs`。本记录只说明该决定和已执行的最小检查，不把公开仓等同于无敏感信息风险。

## 已知披露面

- 历史验收证据包含 `/Users/...`、`/private/tmp/...` 等本机绝对路径。
- 包内包含项目联系邮箱、公开 GitHub 仓位、commit、build 和测试日志。
- v0.1 包包含多层历史 ZIP、RTF 和旧线程交接；原字节保留，未为公开化而重写。
- 根 `LICENSE` 继续适用；公开可见不代表授予复制、修改或再发布许可。

## 2026-07-20 上传前检查

- 四个输入 ZIP：无路径穿越、绝对 ZIP member、symlink、加密 member、精确重名或大小写冲突。
- 对外层和嵌套 ZIP 递归扫描：未发现 private-key banner、GitHub/OpenAI/AWS token、Bearer token、basic-auth URL 或非占位 secret assignment。
- 通用 40 字符模式会命中 SHA-256/commit 等证据标识，因此不作为 secret 判据；已使用带 key/context 的规则复核。

扫描不能证明未来不存在未知格式的秘密。若后来确认真实凭据已进入 Git 历史，必须停止使用、立即轮换并按仓库清史流程处理，不能只删除工作树文件。
