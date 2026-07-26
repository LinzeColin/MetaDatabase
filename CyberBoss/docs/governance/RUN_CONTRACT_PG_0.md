# Run Contract — PG-0 Stage 0 Exit Gate

## 1. Goal

独立判定 Stage 0 exit gate `PG-0`：

> Pinned sources, current architecture, simulators, live-measurement script,
> activation sheet and no-wait policy validate; no credential is required to
> pass repository preparation.

只有上述全部由当前可执行证据证明时，才把 `PG-0` 标为 `passed`。本 Run
不得顺带开始 `P1.1 / CB-100`。

## 2. Minimum scope

- 以精确 P0.5 closure commit
  `7356393cf7fe8281b602c10352a827c15b48b748` 为不可变输入；
- 验证 `CB-000`–`CB-040` 五项 Stage 0 task 均为 `passed`，后续 25 task
  均为 `not_started`；
- 独立复验固定 source bundle、source lock、许可证、Corresponding Source、
  模块地图与无持续 upstream relationship；
- 验证当前架构、唯一 repository/path/data/domain/service/port/bucket/prefix、
  Feature Flags、out-of-scope 和 multi-file authority 无未解决冲突；
- 在 scrubbed credential environment、临时 HOME/CODEX_HOME/WeChat state 下
  运行 simulator、scope/config、activation clean fixture、preflight
  `--check`、resource、DAG、traceability、no-wait、TaskPack、secret scan
  和完整 App regression；
- 将缺失真实激活精确保留为 `activation_pending` / `hazard_blocked`，
  不读取 credential value、不形成全局 wait；
- 扩展全局 Prestage validator，使 `current_run` 能 fail-closed 地表达
  `PG-*` Gate，而不弱化 Task/phase、依赖或 gate→stage task 检查；
- 生成 Gate matrix、原始摘要、validation report 与独立 remote-publication
  只读检查。

## 3. Non-goals

- 不执行 `P1.1 / CB-100` 或任何 Stage 1 implementation；
- 不修改 `CyberBoss/app/**`、`CyberBoss/vendor/**`、固定 source bundle、
  product TaskPack、Acceptance、architecture 或历史 Stage 0 evidence；
- 不安装/部署/启动 OVH CyberBoss Runtime，不创建用户、目录、systemd unit、
  release symlink、DNS、Access、R2/OCI object 或 Status row；
- 不执行真实 Codex/WeChat/Private-MetaDatabase/provider activation；
- 不读取、打印、复制或提交 secret/credential value；
- 不创建 repository、remote、submodule、Git URL dependency 或 upstream
  relationship；
- 不 push，不创建 PR/tag/release，不运行远端 CI；
- 不把 simulator 或 clean missing-credential fixture 称为真实外部成功。

## 4. Inputs to inspect

- `machine/facts/owner_decisions.json`
- `machine/facts/task_state.json`
- `machine/source-lock.json`
- `docs/evidence/CB-000/**` 至 `docs/evidence/CB-040/**`
- `docs/product_design/v0.0.0.4/00_README_FIRST.md`
- `02_PRD_ACCEPTANCE_CONTRACT.md`
- `03_ARCHITECTURE_DATA_SECURITY.md`
- `04_TASK_DAG_EXECUTION_PACK.yaml`
- `05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md`
- `10_TRACEABILITY_RELEASE_CHECKLIST.md`
- `12_CURRENT_ROADMAP.md`
- `implementation-kit/config/**`
- `implementation-kit/scripts/**`
- `implementation-kit/simulators/**`
- `implementation-kit/tests/**`
- `app/package.json`、`app/package-lock.json` 与完整现有 App tests（只读）
- Git branch/worktree/origin 与 remote publication 状态

## 5. Allowed modifications

- `CyberBoss/docs/governance/RUN_CONTRACT_PG_0.md`
- `CyberBoss/docs/evidence/PG-0/**`
- `CyberBoss/scripts/validate_pg0.py`
- `CyberBoss/scripts/validate_prestage0.py`
- `CyberBoss/machine/facts/task_state.json`
- `CyberBoss/README.md`
- `CyberBoss/HANDOFF.md`
- `CyberBoss/CHANGELOG.md`

除以上路径外不得修改。尤其禁止修改 `CyberBoss/app/**`、
`CyberBoss/vendor/**`、`docs/product_design/**`、CB-000–CB-040 evidence、
母仓根文件与其他项目。

## 6. Validation

```bash
python3 CyberBoss/scripts/validate_pg0.py
python3 CyberBoss/scripts/validate_cb000.py
python3 CyberBoss/scripts/validate_prestage0.py
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
git diff --check
```

`validate_pg0.py` 本身还必须在无 credential fixture 中执行 source/App、
simulator、activation、scope、resource、status、secret 与 clean-install
checks；不得用报告中的 PASS 字符串替代真实子进程结果。

## 7. Risks and rollback

- 历史 evidence 漂移：以 P0.5 closure commit 为边界，任何 CB-000–CB-040
  evidence/source/app/vendor 变化均 fail closed；
- 环境中隐式 credential 造成假通过：清除 auth/provider/secret 变量，使用
  临时 HOME、空 CODEX_HOME 和空 WeChat state；Gate pass 不依赖远端 API；
- simulator 冒充 real：真实状态只能保持现有
  `activation_pending` / `hazard_blocked`；
- Gate state schema：Prestage validator 只接受现有 `PG-*`、同名 `gate_id`、
  与 `pass_gates` 一致的状态，并继续要求该 Stage 五项 task 全部 passed；
- 回滚仅 `git revert` 本地 PG-0 commit；没有外部 mutation、remote ref 或
  业务数据需要回滚。

## 8. Stop conditions

- CB-000–CB-040 任一不是 `passed`，或任何 `CB-100` 以后 task 已启动；
- source/license/Corresponding Source/upstream separation 任一 UNKNOWN、
  冲突记录丢失或声称上游已澄清；
- 当前架构、身份、路径、Feature Flag 或 release baseline 存在未解决冲突；
- simulator、App、preflight/resource、activation clean fixture、
  scope/config/security、DAG/traceability/no-wait/TaskPack 任一失败；
- repository preparation 需要真实 credential、外部写入、Mac connector、
  public Runtime、真实时间等待或新 repository；
- 需要修改 app/vendor/TaskPack/历史 evidence 或进入 P1.1 才能过 Gate；
- 需要 push、PR、tag、release、deploy 或执行真实 provider mutation。

## 9. Acceptance

`PG-0` 仅在以下全部成立时为 `passed`：

1. Stage 0 五项 task 均 `passed`；其余 25 task、PG-1–PG-5 均
   `not_started`；
2. exact sources、license、Corresponding Source、129-entry dependency
   inventory、module map 和严格
   `GPL-3.0-only AND AGPL-3.0-only` 冲突处理复验通过；
3. original source/license/conflict record 保留，
   `upstream_clarification_received=false`，所有持续 upstream relation
   switch 为 false；
4. current architecture 与 P0.5 substitutions/flags/conflict scan 一致，
   unresolved conflicts=0；
5. WeChat/Codex simulator contract 4/4、App 155/155、config/scope/Access/
   status tests 全部通过；
6. live-measurement `preflight.sh --check`、resource profile 与有界 pressure
   fixture 可运行且不做 live command/persistent write；
7. activation sheet 包含 device-auth/QR/re-login 边界；空 credential fixture
   返回 Codex/WeChat `activation_pending`、external mutation=0、credential
   values emitted=0；
8. scrubbed environment 下全部非激活 repository preparation 通过，
   secret scan P0/P1/hits=0，无 credential 或全局 wait；
9. DAG、traceability、no-wait、TaskPack、manifests、Prestage 与 PG-0
   validator 全部通过；
10. `PG-0=passed` 后 `P1.1 / CB-100` 仍为 `not_started`，remote branch/PR/tag
    为空，工作树闭环后干净。
