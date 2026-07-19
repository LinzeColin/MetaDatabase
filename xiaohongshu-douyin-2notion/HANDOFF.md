# HANDOFF

## 当前目标

按 v0.0.0.1 Task DAG Stage 0–6 构建 `xiaohongshu-douyin-2notion`；每个 Run 最多一个 Phase，Stage 完成后 Review/Fix/Re-acceptance 才整 Stage 上传。

## 当前状态

- `Stage 0 / Phase 0.1`：PASS。
- `Stage 0 / Phase 0.2`：PASS；只完成 `TSK.x2n.discovery.004`。
- `TSK.x2n.discovery.001–004`：PASS。
- `ACC.x2n.gov.001`：PASS。
- `ACC.x2n.gov.003`：仅当前无制品、零 runtime dependency 范围 PASS。
- `ACC.x2n.dy.003`：Pin/NOTICE/Schema baseline PASS；Adapter Contract Tests 为 DOWNSTREAM_NOT_RUN。
- `ACC.x2n.gov.002`、`ACC.x2n.media.001`、`ACC.x2n.ops.002`：仅基线已建立，下游 Scope 为 NOT_RUN。
- Stage 0 Gate：NOT_RUN；远端 push：禁止。

## 关键决策

- 唯一母仓库/子项目：`LinzeColin/MetaDatabase` / `xiaohongshu-douyin-2notion/`。
- Runtime 与全部下载共用 `X2N_DATA_ROOT`；Owner 解析方式为 home Downloads 下的项目同名目录，绝对值只在私有 marker。
- 旧目录不迁移、不链接、不删除。
- Public Code / Private Runtime；专有/All Rights Reserved。
- Canonical SQLite 是真相源；不持久化媒体 CDN URL、凭据或原始媒体；AI 不创建一级分类。
- xhs exporter 只作 clean-room reference；douyin-downloader 固定 Commit、默认关闭且等待 exact lock/contract；MediaCrawler 只作 external non-commercial research，禁止进入核心或制品。

## 核心文件

- `docs/governance/RUN_CONTRACT_S00_P02.md`
- `docs/governance/UPSTREAM_AUDIT_S00_P02.md`
- `docs/governance/UPGRADE_SHADOW_PLAN.md`
- `docs/governance/READINESS_MATRIX.md`
- `machine/facts/upstream_registry.json`
- `machine/facts/upstream_file_hashes.json`
- `machine/policy/upstream_integration_policy.json`
- `machine/sbom/stage_0_phase_0_2.cdx.json`
- `machine/facts/task_state.json`
- `machine/evidence/stage_0/phase_0_2/verification.json`
- `scripts/verify_phase_0_2.py`

## 验证

```bash
python3 -B scripts/verify_phase_0_2.py --verify-worktree --verify-temp-cleanup --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

Phase 0.2 最后结果：3 个候选 exact pin；27 个关键文件 Commit/blob/SHA-256 可复核；当前 runtime dependency 0、未知 runtime License 0、Unpinned Runtime Upstream 0、xhs 代码复制 0、MediaCrawler bundled false。私有 clone 清理后仓库凭据/认证 remote/上游制品命中均为 0。

## 未解决风险

- Chrome/CWS 当前政策、平台账号边界、Owner Input、Threat Model、ADRs 与最终第三方分发门禁属于 Phase 0.5，仍阻断 G0。
- douyin Adapter 的正常/缺字段/未知字段/错误/超时/Schema drift tests 尚无 Adapter 可测；不得把本轮 baseline 当作完整 `ACC.x2n.dy.003`。
- Owner 分类、Notion、Provider/预算与真实数据规模尚未输入；保守默认已在 Readiness Matrix 登记。
- 尚未运行任何产品代码、真实账号、媒体、模型、Notion、Build、Release 或 Stage 0 Gate。

## 下一步

新 Run 只执行 `Stage 0 / Phase 0.5`：一次性收口 Owner Input、Chrome/CWS 与平台一手政策、Threat Model、ADRs、Stop/Kill Register 和 G0 证据；0.3/0.4 不是独立 Run，不得进入 Stage 1 或上传中间 Phase。
