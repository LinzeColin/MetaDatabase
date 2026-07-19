# HANDOFF

## 当前目标

按 v0.0.0.1 Task DAG Stage 0–6 构建 `xiaohongshu-douyin-2notion`；每个 Run 最多一个 Phase，Stage 完成后 Review/Fix/Re-acceptance 才整 Stage 上传。

## 当前状态

- `Stage 0 / Phase 0.1`：PASS。
- `TSK.x2n.discovery.001–003`：PASS。
- `ACC.x2n.gov.001`：PASS。
- `ACC.x2n.gov.002`、`ACC.x2n.media.001`、`ACC.x2n.ops.002`：仅基线已建立，下游 Scope 为 NOT_RUN。
- Stage 0 Gate：NOT_RUN；远端 push：禁止。

## 关键决策

- 唯一母仓库/子项目：`LinzeColin/MetaDatabase` / `xiaohongshu-douyin-2notion/`。
- Runtime 与全部下载共用 `X2N_DATA_ROOT`；Owner 解析方式为 `Path.home()/Downloads/xiaohongshu-douyin-2notion`，绝对值只在私有 marker。
- 旧目录不迁移、不链接、不删除。
- Public Code / Private Runtime；专有/All Rights Reserved。
- Canonical SQLite 是真相源；不持久化媒体 CDN URL、凭据或原始媒体；AI 不创建一级分类。

## 核心文件

- `docs/governance/RUN_CONTRACT_S00_P01.md`
- `docs/governance/BASELINE_INVENTORY.md`
- `docs/governance/ARTIFACT_RUNTIME_POLICY.md`
- `docs/governance/READINESS_MATRIX.md`
- `machine/facts/task_state.json`
- `machine/evidence/stage_0/phase_0_1/verification.json`
- `scripts/verify_phase_0_1.py`

## 验证

```bash
python3 -B scripts/verify_phase_0_1.py --verify-local-root --verify-worktree \
  --source-roadmap <owner-source-roadmap> \
  --source-taskpack <owner-source-taskpack>
X2N_DATA_ROOT=<owner-private-root> python3 -B -m unittest discover -s tests -p 'test_*.py'
```

最后结果：7 Stage、28 Requirement、35 Task、49 Acceptance；依赖缺失 0、DAG 环 0、旧路由/绝对路径/Secret/CDN/私有文件命中 0；私有根 22 个目录均 Owner-only，真实数据文件 0；6 个临时/可再生目录排除 Time Machine，Canonical/Library/Backups 保持 Included。

## 未解决风险

- 上游 Commit/Schema/License 属于 Phase 0.2；Chrome/CWS、平台政策、Owner Input、Threat Model 与 ADR 属于 Phase 0.5。二者都阻断 G0，不阻断本 Phase。
- Owner 分类、Notion、Provider/预算与真实数据规模尚未输入；保守默认已在 Readiness Matrix 登记。
- 尚未运行任何产品代码、真实账号、媒体、模型、Notion、Build、Release 或 Stage 0 Gate。

## 下一步

新 Run 只执行 `Stage 0 / Phase 0.2`：只读核验上游 Pin、Schema、许可证、NOTICE 与 External Adapter 边界；不得顺带进入 Phase 0.3。
