# Run Contract — P0.1 / CB-000

## 1. Goal

完成固定历史来源、依赖、许可证与官方 Codex 约束审计，准备可恢复且与上游持续关系
完全切断的本地 source bundles，并形成精确到模块的 reuse/change map。

## 2. Minimum scope

- 一次性读取并核验 CyberBoss、timeline-for-agent 及锁定 transitive Git
  dependency 的精确 commit；
- 记录版本、tree/commit SHA、Node engine、lockfile、版权、许可证与文件 manifest；
- 将需要继续使用的源码作为无 `.git`、无 remote、无 submodule 的普通文件导入
  `CyberBoss/app/` 与 `CyberBoss/vendor/`；
- 用本地 `file:`/workspace 方案取代 moving Git dependency，并运行无 secret 安装、
  syntax/test 与 Timeline CLI callable 验证；
- 对微信 poll/cursor/send、Runtime adapter、shared-start、state、Timeline 集成定位；
- 从官方 OpenAI 文档记录 Codex transport/auth 边界与经本地协议验证的最低兼容版本；
- 生成 CB-000 验收证据、source lock、依赖/许可证清单与上游分离扫描。

## 3. Non-goals

- 不执行 `P0.2 / CB-010` 或任何后续 phase；
- 不修改业务行为、cursor 顺序、durable messaging 或云部署逻辑；
- 不测量/修改 OVH、Cloudflare、Private-Database、R2、OCI 或 Status；
- 不使用真实 secret，不运行真实微信/Codex E2E；
- 不 push、不创建 PR/tag/release。

## 4. Inputs to inspect

- `docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml`
- `docs/product_design/v0.0.0.4/02_PRD_ACCEPTANCE_CONTRACT.md`
- `docs/product_design/v0.0.0.4/08_UPSTREAM_CODE_CHANGE_MAP.md`
- `UPSTREAM_PROVENANCE.md` 与 `THIRD_PARTY_NOTICES.md`
- 锁定历史来源 commit、package manifests/lockfiles 与许可证文件
- 官方 Codex CLI/App Server 文档及本机已安装 CLI 协议表面

## 5. Allowed modifications

- `CyberBoss/app/**`
- `CyberBoss/vendor/**`
- `CyberBoss/.gitattributes`（仅登记逐字保留来源文件的精确 whitespace
  例外）
- `CyberBoss/machine/source-lock.json`
- `CyberBoss/machine/facts/owner_decisions.json`（仅固化本 Run 的第三方许可证
  冲突处置决策）
- `CyberBoss/docs/evidence/CB-000/**`
- `CyberBoss/scripts/validate_cb000.py`
- `CyberBoss/scripts/validate_prestage0.py`（使静态 Prestage 基线校验可接受
  合法的后续 Task 状态推进，同时继续验证依赖顺序，并从 source 空文件检查中
  排除 `.git`/`node_modules` 非交付安装元数据）
- `CyberBoss/THIRD_PARTY_NOTICES.md`
- `CyberBoss/UPSTREAM_PROVENANCE.md`
- `CyberBoss/CHANGELOG.md`
- `CyberBoss/README.md`
- `CyberBoss/HANDOFF.md`
- `CyberBoss/machine/facts/task_state.json`
- 本 Run Contract
- 仅为修复已证实旧数据语义或登记证据所需的
  `CyberBoss/docs/product_design/v0.0.0.4/**` 与双 manifest

不得修改仓库根文件或其他项目。

## 6. Validation

```bash
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
npm ci --ignore-scripts
npm test
git diff --check
git status --short
```

安装/测试必须使用本地 source bundle，不得在验证期间解析 Git URL 或跟随分支。

## 7. Risks and rollback

- 锁定依赖可能没有兼容许可证：不导入该依赖，CB-000 保持未通过并保留审计证据。
- npm lifecycle script 可能产生网络/副作用：先 `--ignore-scripts`，仅在脚本审计后运行
  必要的普通测试。
- 上游测试可能依赖 OS/secret：单独标记未激活路径，不得把窄测试冒充全通过。
- 回滚边界是本 Run 的本地文件与 commit；不得改写 PS0.1 或其他项目。

## 8. Stop conditions

- 必需来源 commit 不存在或内容与锁定事实冲突；
- 任一必须导入的许可证为不兼容、缺失或无法归属；
- 微信、Runtime 或 Timeline 核心能力在锁定来源中不存在；
- 需要新增/删除 Task、Oracle 或改变 Stage 1 + Stage 2A 产品范围；
- 需要保留 upstream remote、submodule、moving Git dependency、自动同步或运行时下载。

## 9. Acceptance

CB-000 仅在以下全部成立时为 `passed`：

1. AC-034：既有 timeline tools 在固定本地 bundle 上真实可调用，且没有第二套内核；
2. AC-069：CyberBoss 及所有实际保留依赖的许可证、NOTICE、版本、修改说明与
   Corresponding Source 路径齐全；
3. source lock、文件 manifest、bundle hash、dependency/license inventory 与
   baseline module map 相互一致；
4. 本地安装/测试证明确认不需要 Git URL、upstream remote、submodule、`#main`、
   自动同步或 runtime source fetch；
5. 全局 TaskPack 验证、作用域检查与本合同全部命令通过；
6. `CB-010` 及所有后续 Task 仍为 `not_started`。
