# xhs-douyin-2notion

把用户明确选择的小红书、抖音、哔哩哔哩、快手、微博和淘宝当前内容或个人列表批次，治理为可恢复、可分类、带 ASR/OCR/关键帧证据的 Markdown 与 Notion 知识资产。

项目名是稳定品牌，不是平台范围上限。六平台均采用独立 Policy/Auth/Technical Gate；未知即禁用。这里的在线采集不是通用爬虫：无自动滚动、无账号状态改变、无代理/指纹规避、无凭据或平台媒体 URL/原始媒体持久化。

当前状态：`v0.0.0.1 / Stage 0 / Phase 0.5` 治理制品与合成验证已通过当前范围检查，Stage Gate 仍为 `NOT_RUN`。临时源码 remote 的凭据形态事件已隔离且文件扫描为 0，但 G0 前仍需 Owner 轮换/重新认证或证明凭据已失效。本阶段不包含采集、账号访问、浏览器控制、模型调用、Notion 写入或媒体处理；六平台与所有上游候选均默认关闭且未进入 runtime。与 MetaDatabase 其他长期开发采用显式、零重叠 worktree 隔离，外部文件不进入本项目证据或提交。

## 固定边界

- 母仓库：`LinzeColin/MetaDatabase`
- 子项目：`xhs-douyin-2notion/`
- 下载目的地逻辑名：`X2N_DOWNLOAD_DESTINATION`；原始 taskpack 未指定本机绝对路径
- 数据根逻辑名：`X2N_DATA_ROOT=${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion`（Runtime 与全部下载共用隔离命名空间；真实解析值不进 Git；已有同级条目不触碰）
- 路径名边界：下载父目录名不授权安装、运行或接入同名 `MediaCrawler` 上游
- 真相源：本地 SQLite Canonical Store
- 交互/执行：Chrome Side Panel / Local Companion
- 发布边界：Public Code / Private Runtime，专有许可

## v0.0.0.1 DAG

唯一机器真源是 [`docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml`](docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml)，范围仅为 Stage 0–6。每个普通 Run 最多一个 DAG Task 及其 Acceptance；Stage Review 不执行新 Task。每个 Stage 只有在全阶段复核、修复和重验后才允许上传。

## Phase 0.1 验证

```bash
python3 -B scripts/verify_phase_0_1.py --verify-worktree --allow-external-main-dirty --verify-local-root
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

Owner 本机还须显式传入私有根目录执行本地边界验证；命令和真实路径仅保存在本地 Run 记录，不写入仓库。

## Phase 0.2 验证

```bash
python3 -B scripts/verify_phase_0_2.py --verify-worktree --allow-external-main-dirty --verify-temp-cleanup --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

私有上游快照只在 Run 内用于复核 Git 对象与哈希，验收后必须清理；公开证据不包含真实本地路径、凭据或上游源码。

## Phase 0.5 验证

```bash
python3 -B scripts/verify_phase_0_5.py --verify-worktree --allow-external-main-dirty --validate-owner-input "$X2N_DATA_ROOT" --verify-temp-cleanup --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

下一 Run 只能做 Stage 0 全 Stage Review/Fix/Re-acceptance；G0 未通过前不得进入 Stage 1 或上传。

以上 `--allow-external-main-dirty` 只用于 Owner 已明确要求的长期并行情形，并要求外部 dirty paths 与 x2n 零重叠；正常 clean-main 场景应省略此参数，默认严格门禁保持不变。
