# Run Contract — Stage 1 Foundation 004

- Run ID：`RUN-X2N-S01-F004`
- 唯一 Task：`TSK.x2n.foundation.004`
- 唯一 Phase：`PH.X2N.1.4`
- Task base：`84731bde18495ab20af005bc70d59d5ce73cbe93`
- `origin/main` cutoff：`baac314b7d97369496212ae89057ec107d187f23`
- Run kind：`single_dag_task`
- Stage gate：`G1=NOT_RUN`；本 Run 禁止远端上传

## 1. 目标

在合成、隔离环境中证明 Chrome MV3 Side Panel 能以最小权限把短生命周期请求交给 Local Companion，并在 Service Worker 被终止后仅根据 SQLite Canonical Store 重连、恢复任务状态。Native Host 必须精确绑定开发 Extension ID、严格验证消息且不执行平台访问、任意命令、任意路径或任意 URL。

## 2. 最小相关范围

- `apps/extension/`：MV3 manifest、Side Panel 五个导航入口、页面支持识别、短生命周期 Service Worker。
- `apps/companion/`：Native Messaging stdio gateway、用户级 macOS manifest 安装/卸载计划、原子 request/job ledger 与状态查询。
- `packages/test-fixtures/`、`tests/`、`scripts/`：六平台支持页和不支持页合成 Fixture、Playwright Extension E2E、100 次 worker restart chaos、Host Contract/Fuzz、权限审计。
- `docs/`、`machine/`、`evidence/`：本 Task 的状态、证据和交接。

## 3. 明确非目标

- 不访问真实账号、真实平台页面或账号列表，不执行下载、自动滚动或账号状态变更。
- 不实现 Content Script、平台 Adapter、Notion、模型、ASR、OCR、关键帧、媒体或 Foundation005。
- 不把 Native Host 注册到 Owner 的长期 Chrome，不修改共享浏览器 Profile，不执行 Owner Canary。
- 不写入或读取任何共享凭据；不接触其他项目的认证材料。
- 不向远端 push，不合并/rebase `origin/main`，不处理外部并行工作树的文件。

## 4. 允许修改的文件

- 上述最小范围内与 `TSK.x2n.foundation.004` 直接相关的新增或更新文件。
- Canonical Store 只允许增加不改 Schema 的原子 skeleton Job API；不得写真实内容。
- 历史 verifier 只允许更新“当前路由/当前状态”断言；历史 Acceptance 事实不得改写。

## 5. Acceptance 范围

- `ACC.x2n.ext.001`：`ENV-CI-SYNTH` 必须由隔离 Chromium + Playwright 实测；六平台支持 Fixture 识别率 100%，不支持页无可执行 Save，五个入口可访问，uncaught console error 为 0。`ENV-OWNER-CANARY=NOT_RUN`。
- `ACC.x2n.ext.002`：必须执行 100 次真实 Service Worker 终止/按需重启；SQLite 任务 0 丢失、0 重复、0 错误状态；不能用 worker 全局变量恢复。
- `ACC.x2n.ext.003`：精确 Origin、未知动作、超限、Schema Drift、重复 request、Shell/Path/URL 注入全部达到阈值；只在临时 Runtime 运行。
- `ACC.x2n.ext.004`：权限固定为 `activeTab`、`nativeMessaging`、`sidePanel`；`host_permissions` 为空或不存在；无 `<all_urls>`、`cookies`、`storage`、`scripting`、远程代码。

## 6. 验证命令

```text
npm ci --ignore-scripts
npm run test:extension
PYTHONPATH=apps/companion/src:packages/contracts/src uv run --isolated --frozen --package x2n-companion python -m unittest discover -s apps/companion/tests -p 'test_*.py'
python3 -B scripts/verify_foundation_004.py --verify-worktree --allow-external-main-dirty --write-evidence
python3 -B -m unittest tests.test_foundation_004
历史 Foundation001–003 与 Stage 0 verifier 回归
```

所有 Runtime、Playwright profile、trace、截图和完整日志只能在临时私有目录中生成；Git 证据只保存聚合值与 hash。

## 7. 风险与回滚

- 开发 Extension ID 由仓库内公开 key 固定；未来 Chrome Web Store ID 必须独立登记，未知时禁止注册 Host。
- 安装器默认 `plan`，只有显式 `install --confirm`/`uninstall --confirm` 才写用户级 manifest；本 Run 只在 E2E 自建临时 HOME/Profile 中执行并清理，不写 Owner HOME、共享 Chrome 或长期 Profile。
- 回滚：执行 installer 的显式 uninstall（仅删除其自有、内容匹配的 manifest/launcher），再加载 Foundation001 无行为 manifest；SQLite append-only ledger 保留。

## 8. 停止条件

出现任一条件立即 `FAIL_CLOSED`：

- 需要 wildcard Origin、`<all_urls>`、任意 Shell/Path/URL 输入或远程脚本；
- 需要在 Extension Storage 持久化 Secret、私人正文或唯一任务状态；
- 验收只能依赖共享 Chrome、真实账号、Owner Token 或外部项目写入；
- worker restart 后无法由 SQLite 对账，或重复 request 产生第二个 Job；
- 证据、测试输出或 Git diff 含本机绝对路径、凭据形态、真实内容或媒体 URL；
- worktree 与 `xhs-douyin-2notion/` 外部并行改动发生重叠。
