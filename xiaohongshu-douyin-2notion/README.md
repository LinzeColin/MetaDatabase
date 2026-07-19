# xiaohongshu-douyin-2notion

把用户明确选择的小红书和抖音点赞、收藏及当前内容，治理为可恢复、可分类、带 ASR/OCR/关键帧证据的 Markdown 与 Notion 知识资产。

当前状态：`v0.0.0.1 / Stage 0 / Phase 0.1` 治理基线。本阶段不包含采集、账号访问、浏览器控制、模型调用、Notion 写入或媒体处理。

## 固定边界

- 母仓库：`LinzeColin/MetaDatabase`
- 子项目：`xiaohongshu-douyin-2notion/`
- 数据根逻辑名：`X2N_DATA_ROOT`（Runtime 与全部下载共用；真实解析值不进 Git）
- 真相源：本地 SQLite Canonical Store
- 交互/执行：Chrome Side Panel / Local Companion
- 发布边界：Public Code / Private Runtime，专有许可

## v0.0.0.1 DAG

唯一机器真源是 [`docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml`](docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml)，范围仅为 Stage 0–6。每个 Run 最多一个 Phase；每个 Stage 只有在全阶段复核、修复和重验后才允许上传。

## Phase 0.1 验证

```bash
python3 -B scripts/verify_phase_0_1.py
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

Owner 本机还须显式传入私有根目录执行本地边界验证；命令和真实路径仅保存在本地 Run 记录，不写入仓库。
