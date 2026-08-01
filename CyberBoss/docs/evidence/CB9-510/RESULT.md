# CB9-510 扩展 status 纵向矩阵且禁止配置性伪绿

**AC-026 PASS · AC-035 PASS**（FR-026 / NFR-005）

## 差量

CB9-020 记的缺口：`status-snapshot-writer` 产出 5 个顶层字段，
v0.0.0.9 要 10 个顶层字段 + 15 项能力枚举，
`modes/capabilities/queue/resources/canonical_sync/backups` 全缺。

现在：

| | 之前 | 现在 |
|---|---|---|
| 顶层字段 | 5（v0.0.0.9 契约部分） | **10** + v0.0.0.8 带过来的 `model_usage`/`model_calls` |
| 能力枚举 | 14 | **15**（加 `location_timezone`） |
| 模式维度 | 无 | **OWNER / COMPANION** |
| 格子数 | 14 行 | **15 × 2 = 30 格** |
| 每格字段 | 14 | **17**（加 `mode`/`last_failure_at`/`suggested_action`） |
| `schema_version` | 1 | **2** |

`business_lines` 改名成 `capabilities`——它装的不再是一行一条业务线，
而是「能力 × 模式」的格子。版本号跟着走，老的读法读到 `undefined` 而不是读到半份。

顶层没有正好停在 10 个：`model_usage` 和 `model_calls` 是 v0.0.0.8 的
AC-048 / AC-033 要的，原样带过来。为了让数字凑成 10 而砍掉它们，
是拿一条已通过的验收去换一个整数。

## 双模式为什么不是冗余

30 格里绝大多数两格状态相同。合成一格的话，等访客那条路单独坏了
（provider 换了、额度用完了、席位外的人拿不到 key），矩阵里没有一格能表达它，
于是它不存在。

`owner_codex_runtime` 是唯一结构性单模式的那一项：访客根本够不着 Codex。
对访客报主人的健康度是**串模式的伪绿**，也是最坏的一种——主人看自己那边一直是好的。
证据里 `cross_mode_separation` 是这一格的实测：
`OWNER=activation_pending / COMPANION=not_started(OWNER_ONLY_CAPABILITY)`。

## 禁止配置性伪绿

五段纵向内容的状态**不是调用方给的**，是把回执交给 CB9-500 的
`parity-freshness` 判出来的。调用方传 `state` 传不进去（有测试钉死）。
一台从没跑过的机器上，五段全是 `UNKNOWN`，不是绿也不是红。

`configured: true` 单独一个字段变不成绿——但它承重：
`not_configured` 和 `no_live_receipt` 是两个不同的原因，
前者去把它配上，后者去用它一次。

三个模块（`business-matrix` / `vertical-sections` / `parity-freshness`）
里没有 `writeFileSync` / `INSERT` / `.run(` / `process.env`——
AC-026 的「不得成为写入入口」和「够不着配置」都是**结构保证**，不是「我们没这么写」。

## 两个自己的 bug

**量不到的资源被当成量到了 0。** `Number(null)` 是 `0`，
而 `Number.isFinite(0)` 是 `true`。只写 `isFinite(Number(v))` 的话，
一项没量到的磁盘会显示成「资源充裕」，而实际是我们瞎了。
这正是那个函数的注释在警告的事，第一版还是踩了。
同时补上 `totalDiskBytes`——只有可用字节算不出比例。

**「多一个字段整份拒绝」这条守卫是守空气的。**
`buildStatusSnapshot` 按名字解构，多传的键在进入函数体的那一刻就没了，
于是守卫查的是一个键写死的字面量对象，`missing` 恒为空。
改成先查**原始输入**（`SNAPSHOT_INPUTS` 白名单），
并把字段检查摘成独立的 `assertSnapshotFields`——摘出来才能被直接喂一份缺字段的
payload 钉死。和 `safeObservation` 那次是同一个形状：**要查的是原始输入，
不是解构之后的那个对象。**

## AC-035 建议动作

每一格、每一段都带 `suggested_action`，从一张冻结的 `reason_code → 动作` 表里查。
生成一句「建议」需要模型，而 NFR-005 写死了自愈不依赖 Agent/Token——
生成就等于自愈调了模型，只是换了个地方。

`model_calls: 0` 是实测的，不是声明的。

备份那一段单开一格 `restore_drill_state`：「备份跑过了」和「备份能恢复」是两件事，
而只有后者算数。备份在跑但从没演练过的时候，
`suggested_action` 是 `run_restore_drill`——那是最危险的一格，因为它看起来是绿的。

## 测试

- 新增 `app/test/cb9-510-status-vertical-matrix.test.js`，34 条
- 连带更新 `cb810-status-resource-selfheal.test.js`（AC-032 的数字改成从常量推导）
  和 `inbound-user-admission-e2e.test.js`（改读 `capabilities` + `collapseModes`）
- 全量回归 **1417 + 72 全绿**

## 变异测试

17 刀全红，基线 0（见 `mutation-report.json`）。
两刀第一轮活着，都是真缺口，不是噪声：

- 「状态改成由调用方直接给」——`state` 两边都是 `UNKNOWN`，
  只断言 `state` 的话那个入参不承重。补了 reason 的断言。
- 「顶层少一段也放行」——守卫是死代码（见上）。摘成独立函数才承重。

## 回滚

三个文件改动 + 一个新模块 + 一个新测试文件，无迁移、无数据变更。
回滚 = `git revert` 本次提交；`status` 退回 `schema_version: 1` 的 14 行形态。
v0.0.0.8 的数据和线上 release 不受影响。
