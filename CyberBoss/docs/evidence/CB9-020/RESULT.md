# CB9-020 把 v0.0.0.8 现有实现逐项映射为保留、适配或跳过

**依赖**：CB9-000（AC-039 PASS）｜**环境型**：否

## 重要区分

冻结测试验证的是任务包 **Starter Kit 参考实现**；仓库自己是否满足是**另一件事**。
两栏分开记录，不让前者冒充后者 —— 四条冻结测试全绿，但仓库只满足其中两条。

| Acceptance | 冻结测试 | 仓库实际 | 映射 |
|---|---|---|---|
| AC-001 可信身份模式路由 | 2/2 pass | **PASS** | 保留 |
| AC-020 Timeline 事件完整 | 9/9 pass | **FAIL** | 适配 |
| AC-026 Status 业务矩阵 | 6/6 pass | **FAIL** | 适配 |
| AC-043 公开 Timeline 脱敏 | 6/6 pass | **PASS** | 保留 |

## 两条 PASS 的依据

- **AC-001**：`OWNER_ONLY_CAPABILITIES`/`USER_CAPABILITIES` 互斥能力模型 +
  `admitDurableTurn` 由服务端定身份；`cb640-dual-user-blind-set.test.js` 与
  `inbound-user-admission-e2e.test.js` 覆盖 owner/companion/spoof 三类输入。
- **AC-043**：对 7 个公开面文件（6 模板 + `business-matrix.js`）扫描原始微信 ID、
  绝对路径、token 字面量、真实 thread ID 四类形态，**0 命中**（`projection-scan.json`）。

## 两条 FAIL 的确切差量

- **AC-020**：仓库没有统一的
  `event_id/user_scope/session_key/intent/status/beijing_time` 事件模型；
  `timeline-service` 线上从未写入过。缺口归 **CB9-400**。
- **AC-026**：`status-snapshot-writer` 产出 5 个顶层字段
  `{schema_version, product, version, generated_at, business_lines}`；
  v0.0.0.9 schema 要求 **10 个顶层字段 + 15 项能力枚举**，
  `modes/capabilities/queue/resources/canonical_sync/backups` **全缺**。缺口归 **CB9-510**。

## 回滚

本节点只读核查 + 新增证据目录，未修改任何既有文件；
回滚 = 删除 `docs/evidence/CB9-020/`，不影响 v0.0.0.8 数据与线上 release。
