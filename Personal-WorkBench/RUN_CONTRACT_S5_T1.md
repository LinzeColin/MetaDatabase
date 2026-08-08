# Run Contract — S5-T1 Save Version 私有候选

## 目标

将已通过独立验收的冻结 commit 保存为 ChatGPT Sites 私有 Version，并把 Version、commit、绑定与 smoke 结果写入 `13_evidence/saved_version.json`。本任务不改变公开 audience，不部署生产。

## 最小相关范围

- 冻结候选：当前 `Personal-WorkBench` 的受控源码、测试与无敏感信息的本地证据。
- 本地 P0 复核：`npm run check`、`npm run build`、质量/视觉/恢复、`npm run verify:release`。
- Sites 私有 Version：仅在上游独立 Verifier 裁决和已关联的精确 source commit 均可证实时执行。
- 交接记录：`HANDOFF.md` 与实际 `saved_version.json`（仅真实保存后写入）。

## 当前已验证的本地准备

- `test:unit`、`test:privacy`、`test:modules`、`test:e2e`、`test:quality`、`test:visual`、`test:recovery`、`check`、`build` 与干净环境的 `verify:release` 均已通过。
- `verify:release` 仅输出 `PASS_BUILD_LAST_MILE_READINESS`，其 verdict 为 `NOT_ISSUED_PRE_VERIFIER`；它不是 S4-T3 的独立通过裁决。
- `.dev.vars`、临时测试和构建产物已忽略；候选证据不保留命令输出或本机绝对路径。

## 明确不在本 run 范围

- 不以 Builder 本地检查冒充 S4-T3 独立验收。
- 不创建 Sites Version、修改 Sites 环境变量、改变访问策略或触发生产 Deploy，直到 S5-T1 前提可被真实证据满足。
- 不上传 GitHub；本 run 仅可创建本地冻结 commit。
- 不执行 S5-T2、S5-T3 或后续生产认证/回滚任务。

## 保存前必须同时满足

1. 精确候选 commit 已冻结，工作树干净，`git diff --check` 通过。
2. 独立 Verifier 对该精确 commit 给出真实 S4-T3 裁决；未知项不得计为 PASS。
3. Sites 已关联并可验证该精确 source commit，且保存操作保持私有、不生成公开部署。
4. 保存后由 Sites 版本清单、私有访问检查、commit/binding 对照和 secret-missing 负向检查共同填充真实 `13_evidence/saved_version.json`。

## 停止条件

- 任一 P0/P1 重新打开；候选 commit、证据或 Sites source linkage 不一致；会改变公开 audience；或缺少独立 Verifier 裁决。
- 发生时不写入伪造的 `saved_version.json`，也不触发部署；只保留可复现本地准备结论。
