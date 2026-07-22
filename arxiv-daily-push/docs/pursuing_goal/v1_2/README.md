# ADP v1.2 开发任务包

这是 ADP 当前 Cloudflare 产品线的权威增量开发合同，目录本身就是交付物，不再生成 v1.2 ZIP。

## 读取顺序

1. `PURSUING_GOAL.md`
2. `PRD.md`
3. `TECHNICAL_DESIGN.md`
4. `ROADMAP.md`
5. `TASK_GRAPH.yaml`
6. `ACCEPTANCE_CONTRACT.yaml`
7. 当前任务唯一 Run Contract

`MANIFEST.yaml`、`INPUT_ARCHIVE_MANIFEST.json` 和 `TREE_SHA256.txt` 用于锁定版本及输入；`HISTORICAL_TRACEABILITY.csv` 解释 v0.1、前端 v1.1、HANDOFF 和两轮验收如何进入 v1.2。

## 执行纪律

- WIP=1；严格按 Task Graph 依赖执行。
- 每个任务使用独立分支、Run Contract、测试证据和独立 verifier。
- `NOT_RUN`、`UNKNOWN`、`BLOCKED`、缺阈值或缺 Subject 均不是 PASS。
- S1、S2 已关闭；S3 的独立 `RUN_CONTRACT_03_SCIENCE_ADVANCES_PUBMED.md` 已锁定，当前只允许
  实现 `ADP-V12-S3-T001` 的 Science Advances/PubMed candidate，不顺带做 UI、版本、运维或部署。
- v0.1 和 V7.2 保留为历史/兼容面，不恢复 CodexProject 旧源。

## 本地验证

```bash
python3 arxiv-daily-push/docs/pursuing_goal/v1_2/tools/validate_package.py --repo-root .
python3 arxiv-daily-push/machine/tools/check_dual_plane_ci.py --root . --projects arxiv-daily-push --require-projects
```

正式验收还必须用 verifier v2.1 的 `ingest_taskpack.py` 冻结完整目录、计算完整包与七角色双摘要；builder 运行 ingest 只能作为预检，不能自签 PASS。
