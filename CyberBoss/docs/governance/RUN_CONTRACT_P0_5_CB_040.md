# Run Contract — P0.5 / CB-040

## 1. Goal

冻结 Stage 0 的唯一实现基线与 release plan，使下一 Gate 能从一组无冲突、
可追溯、无真实凭据值的 Canonical Facts 开始。锁定实际 repository、路径、
domain、service、port、bucket/prefix、feature flag、out-of-scope 和 multi-file
authority；输出 `implementation-baseline.md`、实际 environment substitutions、
确定性 10 项 traceability 审计、DAG 输出、本地 baseline commit SHA 与
`GO_TO_PG-0` / `NO_GO` 决策。

## 2. Minimum scope

- 复核 CB-000–CB-030 全部 Stage 0 证据和 `task_state.json` 依赖状态；
- 从 owner decisions、source lock、identity scope、credential slots、host
  evidence、TaskPack 和 operations contract 交叉生成唯一非秘密 substitutions；
- 全仓静态搜索相互冲突的 repository、path、domain、service、port、data
  authority、upstream relationship、Mac connector、real-time soak/wait 和
  scope-expansion 表达；
- 将产品文档中遗留的 Feature Flag 别名最小化对齐到 implementation-kit
  已校验的唯一运行时名称，并重建外层 TaskPack manifest；不改变功能默认值、
  Acceptance、Task DAG 或实现代码；
- 冻结每个后续能力域的 reuse/change 模块、测试、Acceptance 与 release
  artifact，不在本 Run 实现它们；
- 以 baseline commit 的父提交 `539a15e0cbebce6b6dd016316721085576dba0d6`
  固定 P0.4 输入；
- 先创建一个本地 baseline commit，再在同一 P0.5 phase 的闭环 commit 中记录
  其 SHA，解决 Git commit 不能安全自引用的问题；
- 所有外部激活项继续使用 `activation_pending` / `hazard_blocked`，不得成为
  全局等待节点。

## 3. Non-goals

- 不执行 `PG-0`，不开始 `P1.1 / CB-100`；
- 不修改 `CyberBoss/app/**`、`CyberBoss/vendor/**` 或固定 source bundles；
- 不安装、部署或启动 CyberBoss Runtime，不写 OVH、Cloudflare、R2、OCI、
  Private-MetaDatabase、Status 或 DNS；
- 不创建新 repository、remote、submodule、Git URL dependency 或 upstream
  relationship；
- 不注入、读取、打印或提交 credential value；
- 不 push，不创建 PR/tag/release，不运行远端 CI；
- 不把规划文件称为已实现、已部署或已通过后续 Acceptance。

## 4. Inputs to inspect

- `machine/facts/owner_decisions.json`
- `machine/facts/task_state.json`
- `machine/source-lock.json`
- `docs/evidence/CB-000/**` 至 `docs/evidence/CB-030/**`
- `docs/product_design/v0.0.0.4/00_README_FIRST.md`
- `02_PRD_ACCEPTANCE_CONTRACT.md`
- `03_ARCHITECTURE_DATA_SECURITY.md`
- `04_TASK_DAG_EXECUTION_PACK.yaml`
- `05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md`
- `06_OPERATIONS_STATUS_HANDOVER.md`
- `09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md`
- `10_TRACEABILITY_RELEASE_CHECKLIST.md`
- `12_CURRENT_ROADMAP.md`
- `implementation-kit/config/**`
- `implementation-kit/scripts/**`
- `implementation-kit/systemd/**`
- `implementation-kit/github-actions/**`
- `app/package.json`、`app/package-lock.json` 和固定模块目录清单（只读）
- 当前 Git branch/worktree/origin 与远端 publication 状态

## 5. Allowed modifications

- `CyberBoss/docs/governance/RUN_CONTRACT_P0_5_CB_040.md`
- `CyberBoss/docs/evidence/CB-040/**`
- `CyberBoss/scripts/validate_cb040.py`
- `CyberBoss/docs/product_design/v0.0.0.4/01_PRFAQ_STRATEGY_OKR.md`
- `CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md`
- `CyberBoss/docs/product_design/v0.0.0.4/05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md`
- `CyberBoss/docs/product_design/v0.0.0.4/09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md`
- `CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256`
- `CyberBoss/machine/facts/task_state.json`
- `CyberBoss/README.md`
- `CyberBoss/HANDOFF.md`
- `CyberBoss/CHANGELOG.md`

除以上路径外不得修改；尤其禁止修改 `CyberBoss/app/**`、
`CyberBoss/vendor/**`、Task DAG/Acceptance、implementation-kit、母仓根文件和
其他项目。

## 6. Validation

```bash
python3 CyberBoss/scripts/validate_cb040.py
python3 CyberBoss/scripts/validate_cb000.py
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_task_dag.py \
  CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_traceability.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_no_wait.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 CyberBoss/scripts/validate_prestage0.py
git diff --check
```

`validate_cb030.py` 带 P0.4 phase/scope lock，必须在精确 P0.4 commit
`539a15e0cbebce6b6dd016316721085576dba0d6` 的临时合规
`codex/cyberboss-*` branch/worktree 中历史复验；不得在 P0.5 HEAD 上弱化它。

## 7. Risks and rollback

- Canonical Facts 矛盾：按明确 authority 顺序判定，无法判定则 `NO_GO` 并停止
  依赖实现；
- 把 secret slot 当实际值：substitutions 只允许非秘密常量、文件引用和
  pseudonymous target hash；
- 把规划当实现：每行明确 `reuse`、`change_later`、`activation_pending`，
  后续 Task 状态保持 `not_started`；
- baseline SHA 自引用：使用同一 phase 的 baseline + closure 两个本地 commit，
  closure 只记录已经存在的 baseline SHA 与最终验收；
- 回滚只使用本地 `git revert` 对 P0.5 commit；没有外部 mutation、remote ref
  或数据需要回滚。

## 8. Stop conditions

- repository/path/domain/service/port/data authority/upstream 事实出现经过本
  Run 最小规范勘误后仍无法消解的冲突；
- CB-000–CB-030 任一依赖不再为 `passed`；
- 任何 P0.5 输出需要真实 secret value、公开 Runtime、外部写入或新 repository；
- 需要修改 S1 implementation、固定 source、Task DAG/Acceptance、超出已列明
  Feature Flag 别名勘误的 TaskPack 内容或 `CyberBoss/**` 之外；
- AC-056、AC-068 或 AC-070 缺少可执行证据；
- 需要 push、PR、tag、release、deploy 或执行 PG-0。

## 9. Acceptance

`CB-040` 仅在以下全部成立时为 `passed`：

1. CB-000–CB-030 依赖均为 `passed`，CB-100 及以后和 PG-0–PG-5 均保持
   `not_started`；
2. `environment-substitutions.json` 对每个非秘密 repository/path/domain/
   service/port/bucket/prefix/identity 给出唯一值、authority 和状态，secret
   仅保留 file/slot reference；
3. conflict scan 对所有 active deliverables 报告 Canonical Facts 冲突为 0，
   且 no Mac/local connector、upstream relationship 或独立 repo；
4. `implementation-baseline.md` 冻结 MVP flags、out-of-scope、multi-file
   authority、reuse/change 模块、测试与 immutable release/rollback plan；
5. 确定性抽取 10 个 requirements，每个可定位 Requirement→Acceptance→Task
   →Test→Evidence→Release，AC-068 通过；
6. clean missing-activation 状态继续执行，真实 adapter 精确保持
   `activation_pending` / `hazard_blocked`，无全局 wait，AC-056 通过；
7. 全 TaskPack 静态 no-wait 扫描对 real-time soak、7/30-day Gate、fixed-sleep
   Canary 和 waiting-for-credential 命中为 0，AC-070 通过；
8. baseline commit SHA、branch、parent、tree、remote publication=none 有可执行
   证据，closure commit 不篡改该 SHA；
9. go/no-go 只能是 `GO_TO_PG-0` 或 `NO_GO`；不得跳过 PG-0 宣布进入 S1；
10. Git 远端无 CyberBoss branch/PR/tag/push，工作树在闭环后干净。
