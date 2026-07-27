# Run Contract — P4.1 / CB-400 软件正确性流水线

## 1. 不变量与前置锚点

- 产品版本固定为 `v0.0.0.5`；设计基线固定为 `v0.0.0.4`；TaskPack 固定为
  `v0.0.0.7`，ZIP SHA-256 为
  `77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`。
- 本 Run 只执行 `P4.1 / CB-400`，依赖已关闭的 CB-300、CB-310、CB-330、CB-340
  与 Stage 3 独立 Gate `PG-3`。冻结前置 closure 为
  `3845d560591311c7e2b11e77e1dbdfc256486903`；其证据不得重写。
- 不新建 repo、分支事实源、数据仓或第二套测试平台；长期数据仍仅能通过
  Private-Database 的 `private_db_client.py ingest|get|list|verify` 免 clone 路径处理。
  本 Run 不调用该路径。
- 不依赖 macOS `launchd`；不执行 macOS service、Cloudflare、DNS、Timeline、
  Status、R2、OCI、Private-Database 或任何真实运行时/Provider 操作。
- `control_plane_llm_calls=0`、`operations_llm_calls=0` 永久保持；不启用
  Verifier、Teleiosis、Persona、SubAgent、第二模型、动态研究或真实时间等待。

## 2. Skill Router 与单一 Skill 边界

本包 Router 对 `CB-400` 的结果为：

```json
{
  "task_id": "CB-400",
  "selected_skill": "output-skill",
  "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
  "max_lightweight_skill_loads": 1,
  "prohibited_skill_loads": 0,
  "actual_skill_body_loads": 1,
  "fallback": "machine/skill_microplaybooks.json"
}
```

只加载一次本地 `output-skill`，用于完整交付物与交叉检查；实际 Skill body load 为 `1`，
不加载其他 Skill。该 Skill 不提供运行时行为、模型调用、外部连接或事实源。

## 3. 目标与最小实现范围

复用目标仓现有 tests/validators，新增一个 frozen core suite（冻结的本地高风险核心集）：

1. install/build/start 的 loopback、immutable release 与受控 runtime gate；
2. migration compatibility；
3. durable inbox/outbox crash-cut recovery、scheduler singleton 与 canonical
   conflict/privacy；
4. Timeline、Status、Access、backup/isolated restore 与 resource self-heal；
5. rollback discrimination：任何一个切片失败只给出
   `discard_candidate_keep_accepted_baseline`，不修改 deployment pointer；
6. 非阻塞 postdeploy automation：仅定义可手动或 CI 触发的状态/incident/recovery/
   backlog follow-up，`blocking_wait_nodes=0`，不形成观察窗口或下一节点阻塞。

允许的实现路径严格为：

```text
CyberBoss/app/scripts/software-correctness-suite.js
CyberBoss/app/test/software-correctness-suite.test.js
CyberBoss/tests/cloud-runtime-version.test.js
CyberBoss/docs/governance/RUN_CONTRACT_P4_1_CB_400.md
CyberBoss/scripts/validate_cb400.py
```

`cloud-runtime-version.test.js` 只修复其临时 immutable-release fixture 的真实路径
规范化与完整前置条件，确保 Claude 双门在正确的 release/toolchain 边界之后被
测试；它不启用 Claude、Codex 或任何模型。

## 4. Oracle、验证与证据

本节点覆盖 `FA-AC-015`、`FA-AC-018`、`FA-AC-027`、`FA-AC-029`：

- `FA-AC-015`：所有冻结核心切片都必须 PASS；
- `FA-AC-018`：migration/crash-cut/recovery/backup restore 与 rollback
  discrimination 均能区分失败候选；
- `FA-AC-027`：无 blocking wait、固定 sleep、凭据等待或无限 retry；
- `FA-AC-029`：Task → tests → implementation → summary/Subject 的精确绑定。

验证在 scrubbed credential environment 中执行：suite unit、真实冻结核心集、
postdeploy plan、App check/full regression、root core tests、PG-3 revalidation、
identity/config、DAG/traceability/no-wait/TaskPack 与两个 manifest。`--prepare`
只能在 CB-400 尚未关闭时通过；final 还必须验证精确 implementation/closure
commit 边界及 `docs/evidence/CB-400/{summary,subject}.json`。

## 5. 状态、停止与回滚

- 所有外部 activation truth 保持：Private-Database、Cloudflare Access/DNS/Analytics、
  Timeline、global Status、OCI、self-heal/timer 均为 `activation_pending`；R2 为
  `hazard_blocked`。本地 tests 不得将其标绿。
- 任一 core Oracle 不能区分错误实现，或 migration/rollback 不兼容，即停止 closure。
- 本 Run 的回滚是丢弃 CB-400 candidate，保留已接受 baseline；不修改 PG-3 或任何
  已密封证据，不重写公开历史。
- 仅当全部 Oracle 有可复跑、无凭据、Subject 绑定的本地证据时，`CB-400=passed`；
  下一原生节点才是 `CB-410`，并须重新运行自己的包内 Skill Router。
