# Run Contract — P4.3 / CB-420 安全、供应链、隐私与 AGPL Assurance

## 1. 锁定边界

- 产品版本固定为 `v0.0.0.5`；设计基线为 `v0.0.0.4`；TaskPack 为 `v0.0.0.7`，
  ZIP SHA-256 为
  `77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`。
- 依赖为已关闭的 CB-400 closure
  `55192340a3bc80ac979e283a5308daee9158ad3e`；本 Run 只执行 `P4.3 / CB-420`。
- 不新建 repo、供应链平台、SBOM 真源、数据库、运行时或模型路由；不 clone
  Private-Database。现有 source-lock、CB-000 完整 dependency/license inventory、
  license 文件和 Access/Analytics policy 是唯一输入真源。
- 不依赖 macOS `launchd`；不执行 Cloudflare、R2、OCI、Private-Database、
  Timeline、Status、DNS、服务、真实 release 分发或真实 Runtime 操作。
- 控制面与运维模型调用永久为 `0`。不使用 Verifier、Teleiosis、Persona、
  SubAgent、第二模型、动态研究或真实时间等待。

## 2. Router 与唯一 Skill

本包 Router 对 `CB-420` 返回：

```json
{
  "task_id": "CB-420",
  "selected_skill": "output-skill",
  "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
  "max_lightweight_skill_loads": 1,
  "prohibited_skill_loads": 0,
  "actual_skill_body_loads": 1,
  "fallback": "machine/skill_microplaybooks.json"
}
```

只使用本地 `output-skill` 一次；实际 Skill body load 为 `1`。不加载其他 Skill，
不调用其外部能力。

## 3. 最小确定性输出

新增只读 `canonical-security-assurance` evaluator 和 CLI，严格产生三类输出：

1. security report：扫描 app/source/machine 的高置信 secret 模式与本地 env 文件，
   并固定记录 P0/P1 finding、控制面/运维 LLM 与 macOS 依赖计数；
2. SBOM：复用 `docs/evidence/CB-000/dependency-license-inventory.json` 作为
   唯一完整 129-component inventory，输出其 hash、lockfile hash、component digest、
   unresolved-license count 与 strict dual-license count；
3. Corresponding Source package：以当前 `CyberBoss` 源码树作为唯一权威 package，
   输出相对路径 per-file SHA-256 manifest、三份锁定 source bundle、原许可证和
   `AGPL-3.0-only AND GPL-3.0-only` conflict closure。不会制造复制 archive 或
   平行 source/SBOM 真源。

它还复用 CB-320 的 Access/runtime 与 Analytics guard：外部 `8765` 仍不可达，
匿名/直连 origin 由既有 contract 拒绝，Analytics 只接受 aggregate page-view/
performance fixture，禁止 thread/job ID、private content、URL query/fragment 和
第二 analytics database。Cloudflare Web Analytics 与 release distribution 都为
`activation_pending`；该状态不等于启用或真实外部验证。

允许的 implementation 路径严格为：

```text
CyberBoss/app/scripts/security-assurance-suite.js
CyberBoss/app/src/services/assurance/canonical-security-assurance.js
CyberBoss/app/test/canonical-backup-runtime.test.js
CyberBoss/app/test/canonical-security-assurance.test.js
CyberBoss/docs/governance/RUN_CONTRACT_P4_3_CB_420.md
CyberBoss/docs/governance/SUPPLY_CHAIN_ASSURANCE_CB_420.md
CyberBoss/scripts/validate_cb420.py
CyberBoss/tests/security-assurance-suite.test.js
```

## 4. Oracle、验证、停止与回滚

本节点映射 `FA-AC-011`、`FA-AC-017`、`FA-AC-028` 与 `FA-AC-032`，在
`local_deterministic_only` 范围内验证：

- 高置信 secret/privacy hit、env file、未接受 P0/P1 finding、unresolved license
  均为 `0`；whereabouts 的 strict dual-license conflict 保持未解决但完整保留；
- 129-component canonical inventory、source-lock 三个 bundle、license 与
  Corresponding Source package manifest 完整且可重算；
- loopback Runtime、Access deny/origin-bypass 与 analytics privacy fixture 继续
  fail closed；
- CLI、App/root tests、既有 Access/workspace/runtime tests、CB-400 anchor、
  App regression、identity/config/DAG/traceability/no-wait/TaskPack/manifests 全部通过。

任何 high-confidence secret、许可证闭包缺失、未接受 P0/P1、Access/8765 边界
失效或 analytics privacy 漏检都停止 closure。回滚只丢弃 CB-420 candidate，
保持既有 source-lock、license、dependency inventory 和 CB-410 baseline；不改写
已密封 evidence。真实外部 activation 保持 pending，下一原生节点仅能是 CB-430，
并须先运行该任务自己的 Router。
