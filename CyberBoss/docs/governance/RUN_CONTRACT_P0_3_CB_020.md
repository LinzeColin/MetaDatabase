# Run Contract — P0.3 / CB-020

## 1. Goal

锁定 `LinzeColin/MetaDatabase` 内 `CyberBoss/` 的唯一代码身份、workspace
write scope、Private-MetaDatabase no-clone 数据边界，以及 Cloudflare
DNS/Access/Analytics/R2 与 OCI 的最小权限、幂等 activation contract 和
credential slots。以负向测试证明越界、匿名访问、secret 泄漏和宽权限均
fail closed。

## 2. Minimum scope

- 固定 `alias=cyberboss`、`repo=LinzeColin/MetaDatabase`、
  `project_subpath=CyberBoss`、`write=CyberBoss/**`；
- 固定 `LinzeColin/Private-Database@main/Private-MetaDatabase`、
  `domain=CyberBoss`，且只允许 `private_db_client.py`
  `ingest/get/list/verify` 免 clone 协议；
- 建立不含真实值的 credential-slot inventory、文件权限与用途合同；
- 建立 Cloudflare DNS/Access/Analytics/R2 与 OCI 的可验证、幂等、默认
  plan-only activation adapters 和 local mock endpoints；
- Access policy 默认 deny，只有明确 Owner identity 或 service token
  policy 可 allow；DNS 不得先于 Access；
- 对 repository/path/domain/area/operation/bucket/prefix/key/identity 做
  allowlist 与负向测试；
- 运行 secret/DLP/security/no-wait/source-offer/license/NOTICE/dependency
  回归，覆盖 AC-043、AC-056、AC-065、AC-069；
- 若外部 credential 缺失或无法证明最小权限，只将对应 adapter 标为
  `activation_pending`，其他实现与验收继续。

## 3. Non-goals

- 不创建、fork、clone 或恢复任何 CyberBoss 独立 repository；
- 不 clone `Private-Database`，不写真实 Private-MetaDatabase 数据；
- 不在仓库保存或输出 token、secret、private key、真实 email/account ID；
- 不购买资源，不创建收费 bucket，不公开新服务或网络端口；
- 不在 Access 之前创建 DNS route，不允许 anonymous management exposure；
- 不安装/部署/启动 CyberBoss Runtime，不修改 OVH 服务；
- 不执行 `P0.4 / CB-030`；
- 不 push，不创建 PR/tag/release。

## 4. Inputs to inspect

- `04_TASK_DAG_EXECUTION_PACK.yaml` 的 `CB-020`
- `02_PRD_ACCEPTANCE_CONTRACT.md` 的 AC-043、AC-056、AC-065、AC-069
- `03_ARCHITECTURE_DATA_SECURITY.md`
- `06_OPERATIONS_STATUS_HANDOVER.md`
- `09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md`
- `10_TRACEABILITY_RELEASE_CHECKLIST.md`
- `implementation-kit/config/`
- `implementation-kit/simulators/`
- `implementation-kit/tests/validate_config.js`
- `docs/evidence/CB-000/` 与 `validate_cb000.py`
- `machine/facts/owner_decisions.json`、`task_state.json`
- 本机 `_protected` 既有部署记录、credential 文件存在性/权限和 provider
  identity/permission metadata；不得复制或输出真实值
- Cloudflare 与 OCI 当前官方 API/CLI 文档

## 5. Allowed modifications

- `CyberBoss/docs/governance/RUN_CONTRACT_P0_3_CB_020.md`
- `CyberBoss/docs/evidence/CB-020/**`
- `CyberBoss/machine/facts/task_state.json`
- `CyberBoss/scripts/validate_cb020.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/**`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/**`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/**`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/**`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md`
- `CyberBoss/docs/product_design/v0.0.0.4/06_OPERATIONS_STATUS_HANDOVER.md`
- `CyberBoss/docs/product_design/v0.0.0.4/09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md`
- `CyberBoss/README.md`
- `CyberBoss/HANDOFF.md`
- `CyberBoss/CHANGELOG.md`

不得修改 `CyberBoss/app/`、`CyberBoss/vendor/`、母仓根文件或其他项目。

## 6. Validation

```bash
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_identity_scope.py
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_external_adapters.py
node --test CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/access-policy-contract.test.js
node CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/workspaces.json.example
python3 CyberBoss/scripts/validate_cb020.py
python3 CyberBoss/scripts/validate_cb010.py
python3 CyberBoss/scripts/validate_cb000.py
python3 CyberBoss/scripts/validate_prestage0.py
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_task_dag.py \
  CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_traceability.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_no_wait.py \
  CyberBoss/docs/product_design/v0.0.0.4
git diff --check
```

## 7. Risks and rollback

- 宽权限 credential 被误当成最小权限：只读检查 provider identity/permission
  metadata；无法证明精确 scope 时不 apply。
- DNS 先暴露、Access 后补：activation plan 强制 Access application/policy
  verified 后才允许 DNS mutation；本 Run 不需要公开 route。
- adapter 输出 credential/response body：日志仅保留状态、权限集合、资源哈希
  与计数，禁止 header/body/token。
- local mock 被冒充真实激活：每份 evidence 明确
  `fixture`、`read_only_verified`、`activation_pending` 或 `verified`。
- source-offer/license 回归：复用 CB-000 完整 validator，不修改固定 source。
- 本地回滚为本 Run commit；若任何外部 staging mutation 实际发生，只按
  adapter 输出的 exact resource identity 逆序删除，不动既有资源。

## 8. Stop conditions

- 只有 account-wide/broad write credential，无法证明 zone/bucket/prefix scope；
- 下一步会购买资源、公开新服务/端口或要求 anonymous management exposure；
- 目标 account/zone/bucket/namespace identity 不唯一；
- 操作不是幂等且不能在 mutation 前证明当前 state；
- 任何 secret、private key、真实身份或 raw provider response 将被输出/提交；
- 需要 clone Private-Database、创建新 repo 或扩展到 `CyberBoss/**` 外；
- AC-043、AC-056、AC-065、AC-069 任一出现未处置的失败。

## 9. Acceptance

`CB-020` 仅在以下全部成立时为 `passed`：

1. 唯一代码/workspace/data identity 由 machine-readable policy 与实际 Git
   state共同证明，所有越界 repo/path/alias/area/domain/operation 请求被拒绝；
2. R2/OCI bucket/prefix/key 与 Cloudflare zone/route/Access policy 均
   fail closed，activation adapter 默认 plan-only 且 repeated plan/apply
   不产生重复资源；
3. Access fixture 对 anonymous/unapproved identity 为 deny，对唯一 approved
   placeholder identity/service token policy为 allow；deny/allow screenshot
   标明 fixture 或真实证据类别；
4. credential slots 完整、无真实值、目标 mode/owner 明确，secret scan 与
   forbidden prompt/path/PII scan hits=0（AC-043）；
5. 缺失微信/Codex/Cloudflare/R2/OCI credential 的 clean fixture 仍运行全部
   非激活测试，只有对应 adapter 为 `activation_pending`，无 waiting node
   （AC-056）；
6. port/secret/workspace/provider scope security suite 无 P0/P1 finding
   （AC-065）；
7. source offer、AGPL/GPL conflict record、原许可证、NOTICE、129 项依赖版本
   和固定 source identity 继续由 CB-000 executable regression 证明
   （AC-069）；
8. 外部 activation 只有在现有 least-privilege credential 和无公开/付费/
   不可逆动作时才可 verified；其他精确标记 `activation_pending`，不得冒充；
9. CB-030 及后续 Task、PG-0–PG-5 均未推进。
