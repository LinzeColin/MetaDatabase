# Run Contract — Stage 2 Skeleton 001

- Run ID：`RUN-X2N-S02-S001`
- 唯一 Task：`TSK.x2n.skeleton.001`
- 唯一 Phase：`PH.X2N.2.1`
- Task base：`6777c8fcce75a36741b70c2858c8bc5fff17d440`
- `origin/main` cutoff：`6777c8fcce75a36741b70c2858c8bc5fff17d440`
- Run kind：`single_dag_task`
- Stage gate：`G2=NOT_RUN`；本 Run 禁止远端上传

## 1. 目标

实现小红书用户明确选择的“当前详情页”最小 clean-room 链路：从当前 URL 与可见 DOM
建立稳定 Content ID，输出无 Query/Fragment 的规范页地址、净化标题或显式 null、内容
类型与字段状态；页面结构或身份信号不一致时返回稳定 `X2N_PLATFORM_CHANGED`，且不创建
Native Job。

## 2. 最小相关范围

- Chrome MV3 Extension 的 URL 识别、隔离世界 DOM 提取、Side Panel 当前页动作与 Native
  Messaging 接线。
- 5 个公共安全合成 DOM Fixture：图文、视频、缺字段、稳定 ID 冲突、feed-card 误捕。
- `activeTab` 用户动作前后负向/正向 E2E、Native Host/SQLite 队列与 100 次 Service
  Worker 重启回归。
- 全量门禁重放所需的最小 Native Host/SQLite 并发稳定性修复：只处理已经消失的 transient
  `-wal/-shm` sidecar；Canonical DB 或仍存在 sidecar 的权限加固错误继续 Fail Closed。
- 当前 Manifest 只在 Stage 1 的 3 个权限上增加 `scripting`；仍无 `host_permissions`、
  静态 Content Script、Extension Storage、Cookie、Tabs、Downloads 或远程代码。
- 平台能力位为 `ci_synth_only`。真实小红书页面、Owner Chrome 与账号继续禁用。

## 3. 明确非目标

- 不执行 `TSK.x2n.skeleton.002` 或任何列表、Adapter、分页、下载、媒体、ASR/OCR、分类、
  Markdown、Notion 或真实 Sink。
- 不访问真实账号、Owner Chrome/Profile、平台网络或真实内容；不自动滚动，不改变账号状态。
- 不读取、显示、使用、修改、删除或轮换共享认证材料；不触碰其他项目或竞品工作树。
- 不把当前页 payload、DOM、页面 Query/Fragment、媒体地址或标题持久化到 SQLite；当前
  Native skeleton 仅保存请求 Hash 与可恢复 Job 身份。
- 不执行 G2 Review，不 push、merge、rebase 或发布。

## 4. Acceptance 解释

- `ACC.x2n.capture.001`：ENV-CI-SYNTH 的 5/5 Fixture 必须通过；3 个 ready Fixture 的稳定
  ID、Host/Path、标题/null 与内容类型逐项匹配，2 个改版/误捕 Fixture 必须返回
  `platform_changed`；Query/Fragment 和媒体/raw DOM 返回面为 0。ENV-OWNER-CANARY 所需
  真实图文/视频各 1 未获授权，明确记录为 `NOT_RUN`，因此真实页面 Flag 保持关闭。
- `ACC.x2n.ext.001`：CDP 只作为隔离 E2E 驱动触发 Chromium 默认 Extension Action；Action
  前脚本注入和采集请求均拒绝，Action 后才获得临时 `activeTab` 并允许一次合成当前页
  采集。无持久 Host Permission，测试 Flag 不进入产品 Manifest。
- Stage 1 `ACC.x2n.ext.001/.004` 历史证据不改写；历史 verifier 同时固定旧提交的 3 权限
  事实，并验证当前 4 权限最小白名单。

## 5. 验证命令

```text
npm ci --ignore-scripts
uv sync --frozen --all-packages --group ci
npm run self-test --workspace @x2n/extension
npm run test:xhs-fixtures --workspace @x2n/extension
npm run test:e2e --workspace @x2n/extension
python3.12 -B scripts/verify_skeleton_001.py --verify-worktree --allow-external-main-dirty --require-evidence
python3.12 -B -m unittest discover -s tests -p 'test_*.py'
python3.12 -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir <ignored-or-temporary-directory>
```

浏览器和 Native Host 测试只使用临时 HOME/Profile/Runtime、公共合成页面与拦截响应；
依赖命令使用环境 allowlist，不继承认证变量。截图与 trace 在临时目录销毁，证据仅保留
大小和 Hash。

## 6. 风险、回滚与停止条件

- 风险：DOM drift、详情页与 feed card 混淆、稳定 ID 冲突、Query token 泄漏、Action 前
  越权注入、Manifest 权限扩大、历史 Stage 1 门禁误报。
- 回滚：把 `xiaohongshu_current_page` 从 `ci_synth_only` 设为 `false`，revert 本 Task 本地
  commit；保留合成 Fixture 作为未来修复 Oracle。没有真实 Runtime、账号或外部副作用
  需要回滚。
- 稳定 ID 需要绕过、持久 Host Permission、Cookie/Profile 导出、自动滚动、账号状态
  改变、真实平台调用、Secret/CDN/Runtime 写入或 Owner Canary 冒充通过时立即
  `FAIL_CLOSED`。
