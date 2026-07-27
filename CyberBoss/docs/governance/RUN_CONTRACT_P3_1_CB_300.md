# Run Contract — P3.1 / CB-300 Timeline canonical projection

## 1. Goal

关闭原生任务 `CB-300`：把既有、锁定的 `timeline-for-agent` renderer 适配为
从 CB-240 canonical `timeline-source.ndjson` 可重复构建的只读 Timeline 投影。
本 Run 只交付 projection/build/search 与 rebuild contract；Timeline 不得成为第二
事实源，也不得写回 canonical。

产品版本固定为 `v0.0.0.5`，设计基线固定为 `v0.0.0.4`，TaskPack 固定为
`v0.0.0.7`（zip SHA-256：
`77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`）。
前置 PG-2 已在 closure commit
`f3848fd3b694871f04aba59838704fe91f27cdc0` 精确关闭。

## 2. Router and execution boundary

在本 Run 起点已经运行本包 Skill Router：`task_id=CB-300`、
`selected_skill=webapp-testing`、`mode=NATIVE_IF_PRESENT_ELSE_EMBEDDED`、
`max_skill_body_loads=1`。当前环境不存在该 Skill，因此按 TaskPack 的冻结 fallback
只使用 `machine/skill_microplaybooks.json` 中的 existing HTTP/DOM/unit fixture
路径；实际 Skill body load 为 `0`，不安装、不替换、不联网寻找其它 Skill。

不调用 Verifier、Teleiosis、Persona、SubAgent、第二模型或动态研究。本 Run 最多
关闭一个 phase；完成后下一边界只能是 `P3.2 / CB-310`。

## 3. Implementation contract

- 只读取 CB-240 格式的 `schema_version=1`、`source=cyberboss-canonical` NDJSON；
  未知字段、来源不匹配、同 event ID 不同 record hash 或无效记录必须 fail closed；
- 仅输出固定中文事件标题、日期、终态与 hash 派生的 opaque public ID；不得输出
  event ID、job ID、summary、record hash、prompt、workspace 或 raw canonical 内容；
- 使用锁定 `timeline-for-agent` 的 `buildTimelineDashboard` 和 taxonomy，不调用
  `TimelineService.write`、上游 `write`、store save、dev watcher 或任何 canonical
  写路径；`direct_canonical_writes=0`；
- build digest 是内容寻址的确定性去重键：同一 canonical input 复用既有 release，
  changed input 才构建一次；没有 timer、sleep 或真实时间 debounce gate；
- 在 staging 目录生成静态站点、projection、search index 和 manifest，经 fsync/rename
  原子发布；失败后只读取精确 `last-good.json` 指针，不覆盖 last-good；
- 静态站点默认中文；空 canonical input 显式显示“暂无可公开的时间线事件。”，不得
  落入上游 demo data；搜索只读 derived search index。

映射的 acceptance：

- `FA-AC-008`：稳定 rebuild digest、轻量搜索、last-good fallback、零 canonical 写；
- `FA-AC-028`：静态产物和 evidence 无 secret/完整私聊或 private input 回流；
- `FA-AC-031`：Timeline golden path 与空态均为中文。

## 4. Non-goals and invariants

- 不修改产品版本、设计基线、TaskPack、锁定 vendor source、既有 CB/PG evidence 或
  旧 Timeline 事实库；不新建仓库、submodule、Git URL dependency、数据库或平行事实源；
- 不 clone Private-Database，不执行真实 Private-Database、R2、OCI、Cloudflare、
  WeChat、Codex、OVH 或 GitHub 操作，也不读取、打印或落盘 credential value；
- 不依赖 Mac/macOS `launchd`、Keychain、本机 Runner、隧道或常驻浏览器；不启动
  dev watcher 或真实静态服务；
- 控制面与运维模型调用永久为 `0`；不使用 sleep、Soak、观察期、无限重试、凭据等待
  或其它真实时间等待；
- Timeline/Access/Private-Database/R2/OCI 的真实外部 activation 均保持
  `activation_pending`（R2 继续 `hazard_blocked`），不得伪绿；不 push、PR、tag 或
  release。

## 5. Allowed modifications and rollback

实现提交只允许变更：

- `CyberBoss/app/src/services/timeline/canonical-timeline-projection.js`
- `CyberBoss/app/scripts/canonical-timeline-build.js`
- `CyberBoss/app/test/canonical-timeline-projection.test.js`
- `CyberBoss/tests/canonical-timeline.test.js`
- `CyberBoss/docs/governance/RUN_CONTRACT_P3_1_CB_300.md`
- `CyberBoss/scripts/validate_cb300.py`

closure 提交仅允许变更 `README.md`、`HANDOFF.md`、`CHANGELOG.md`、
`machine/facts/task_state.json` 和 `docs/evidence/CB-300/{summary,subject}.json`。
回滚为禁用该 projection 并恢复上一 `last-good.json` 指向的静态制品；必要时只可
`git revert` 本地 CB-300 closure commit。任何第二权威、canonical write、静态私密
内容或无 last-good 的失败发布均立即停止。

## 6. Validation

```bash
python3 CyberBoss/scripts/validate_cb300.py --prepare
python3 CyberBoss/scripts/validate_cb300.py
git diff --check
```

验证器在移除 credential 名称环境变量的临时目录中实际运行：Timeline projection
unit/DOM fixture、root CLI build/search fixture、Node syntax check、完整 App check/
regression，以及 identity/config/DAG/traceability/no-wait/TaskPack checks。浏览器
能力降级不会阻塞此任务，但只可使用现有 fixture；不得因此增加依赖或建立常驻服务。
