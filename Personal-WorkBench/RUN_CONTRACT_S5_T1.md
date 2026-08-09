# Run Contract — S5-T1 Save Version 私有采证候选

## 目标

依 [PWB-S4-S5-SEQUENCE-001](./ACCEPTANCE_SEQUENCE_ADDENDUM.md)，将通过 S4-T3A 独立就绪审查的冻结项目树保存为 ChatGPT Sites 私有 Version，并把 Version、源/投影 commit、绑定与 smoke 结果写入 13_evidence/saved_version.json。默认使用冻结 MetaDatabase commit；仅当其母仓历史被 Sites 源码服务拒绝且 [PWB-S5-SOURCE-PROJECTION-001](./SOURCE_PROJECTION_CONTRACT.md) 已通过时，可使用其 tree-identical project-root projection commit。无论哪种路径，本任务不改变公开 audience，不部署生产，也不构成最终 15/15 验收。

## 最小相关范围

- 冻结候选：当前 `Personal-WorkBench` 的受控源码、测试与无敏感信息的本地证据。
- 本地 P0 复核：`npm run check`、`npm run build`、质量/视觉/恢复、`npm run verify:release`。
- Sites 私有 Version：仅在上游 `S4-T3A` 独立 `READINESS_PASS` 和已关联的精确 source commit 均可证实时执行。
- Source projection（仅兼容路径）：npm run verify:source-projection 已通过，且 future evidence 同时记录冻结 MetaDatabase commit/root tree/project tree 与实际 Sites projection commit/tree。
- 交接记录：`HANDOFF.md` 与实际 `saved_version.json`（仅真实保存后写入）。

## 当前已验证的本地准备

- `test:unit`、`test:privacy`、`test:modules`、`test:e2e`、`test:quality`、`test:visual`、`test:recovery`、`check`、`build` 与干净环境的 `verify:release` 均已通过。
- `verify:release` 仅输出 `PASS_BUILD_LAST_MILE_READINESS`，其 verdict 为 `NOT_ISSUED_PRE_VERIFIER`；它不是 S4-T3 的独立通过裁决。
- `.dev.vars`、临时测试和构建产物已忽略；候选证据不保留命令输出或本机绝对路径。

## 明确不在本 run 范围

- 不以 Builder 本地检查或 S4-T3A 冒充 S6-T1 最终独立验收。
- 不创建 Sites Version、修改 Sites 环境变量、改变访问策略或触发生产 Deploy，直到 S5-T1 前提可被真实证据满足。
- 不上传 GitHub；本 run 仅可创建本地冻结 commit。
- 不执行 S5-T2、S5-T3 或后续生产认证/回滚任务。

## 保存前必须同时满足

1. 精确候选 commit 已冻结，工作树干净，`git diff --check` 通过。
2. 独立 Verifier 对该精确 commit 给出 S4-T3A `READINESS_PASS`；该结果只允许私有采证，未知项仍不得计为最终 PASS。
3. Sites 已关联并可验证该精确 source commit；若使用 projection，必须先验证 projection tree 与冻结项目 tree 完全相同，并同时回读两段身份，且保存操作保持私有、不生成公开部署。
4. 保存后由 Sites 版本清单、私有访问检查、source/projection commit/tree/binding 对照和 secret-missing 负向检查共同填充真实 13_evidence/saved_version.json。

## 停止条件

- 任一 P0/P1 重新打开；候选 commit、证据或 Sites source linkage 不一致；会改变公开 audience；或缺少 S4-T3A 独立就绪裁决。
- 发生时不写入伪造的 `saved_version.json`，也不触发部署；只保留可复现本地准备结论。
