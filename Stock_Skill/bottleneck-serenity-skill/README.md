# bottleneck-serenity-skill

把公开市场投资主题转换为可审计、可证伪的瓶颈研究 thesis 的 source-only Codex Skill 项目。它先证明系统约束，
再检验稀缺持续时间、上市公司能否把租金转为完全稀释每股自由现金流，以及当前价格是否已反映该情景。

- Stable ID / invocation：`bottleneck-serenity-skill` / `$bottleneck-serenity-skill`
- Version：`0.0.0.1`；display/release label：`v0.0.0.1`
- Canonical Skill：`task-pack/skill_draft/bottleneck-serenity-skill/`
- Distribution：`SOURCE_ONLY`；local install：`PROHIBITED`
- Registry claim：`bottleneck-serenity-skill=0.0.0.1`
- 当前交付状态：`REGISTRY_ACTIVE / STAGE_2_PUBLISHED / STAGE_3_REREVIEW_8_FAILED_REMEDIATION_9_REQUIRED / SOURCE_ONLY / NOT_INSTALLED`

Stage 2 sealed commit `e88f6afd1c025c32bf0ba4b0c3f6ff9250083335` 已 push 到 draft PR #76；无凭据
clean sparse clone、release/hash DAG、远端 head 与两项 CI 均通过。Stage 3 已在本地完成 deterministic、
Trigger、Security、Historical E2E、独立 Forward test 与整体 Review。T002 完成首轮整改后，T003 在
172-path/184-file 冻结双 digest subject 上独立重审。`S3-R004`–`S3-R007` 已关闭；T004 随后用共用
presentation hard gate、current v18 前置 provenance 与 actual-return exact replay、以及 public
session-metadata plain/ZIP safety gate 完成第二轮整改。T005 随后在 227-path/237-file 新双 digest subject
上独立重审：`S3-R003/S3-R008` 已关闭，但 `S3-R001` 的 company/URL 变体与 `S3-R002` 的
allow/exclude-context 语义 mutation 仍 fail open，两项回到 `OPEN`，Re-review 2 verdict=`FAIL`。
T006 已使 Historical/Forward 两个面各 15 类 company/URL 变体 fail closed，并逐字有序绑定四条 allowed
与六条 excluded context。T007 在 228-path/238-file 新双 digest subject 上判定 Re-review 3=`FAIL`：
embedded/lowercase unknown issuer 仍可穿透，合法 role-neutral prose 与正式 template 被误杀，v18
provenance 仅为 host-local，canonical/ZIP 各仍有 10 个 top-level `session` 对象，且许可发现面存在
target-count 冲突。T008 已用显式 entity grammar、DigiCert RFC3161 前置时间戳、fresh v19 executor/双 judge、
session-object/UUIDv4 public safety gate 与动态 license-count Oracle 完成整改。T009 在
244-path/254-file 冻结双 digest subject 上独立重审后仍判 `FAIL`：`S3-R001/R002/R008/R009` 未关闭，
并新增追溯表漏列 T009 verifier 的 `S3-R011`；`S3-R010` 已关闭、`ACC-S2-010` 恢复 PASS。T010 已用
声明式 issuer/entity 句式与 role-neutral allowlist 修复 presentation 双向误判；用前后两枚 DigiCert
RFC3161 时间戳、host receipt、exact provider-return bytes 与失败谱系绑定 provider 验证候选；
public-safety 同义 metadata plain/ZIP 矩阵和由 Task Graph 推导的 ACC-S3 verifier Oracle 也已补齐。
T011 在 269-path/279-file 冻结双 digest subject 上独立重审后仍判 `FAIL`：presentation gate 对 40 个新
issuer 负例全部漏放且误杀 4 个合法正例，public scanner 漏放 16 个私有 metadata 同义键，未签名/
未认证来源的 provider-return 与 host-receipt 即使被 RFC3161 post seal 封存也不能证明真实 provider
execution；owner-facing 许可计数曾与动态报告失配。`S3-R011` 已关闭；
T012 已用共用 semantic role-slot scanner 与 46-negative/9-positive Oracle 修复 presentation 双向误判；
把 v22 明确降级为非 provider-generation proof，并新增要求 T013 现场运行的 sandboxed v23
provider-generation protocol；public-safety 已覆盖私有 metadata 语义同义键，README 也纳入动态许可
计数 Oracle，四份 owner-facing 文档与 committed report 在 T012 时统一为 278 targets。
T013 已在 276-path/286-file 冻结双 digest subject 上完成 Re-review 6。现场 v23 provider-generation
protocol 与四仓 fresh full-history 许可重算通过，`S3-R002/R010` 已关闭；但独立新鲜探针复现
20/20 命名 issuer/rent 负例漏放、12/12 role-neutral 正例误杀，以及 12 类新私有 metadata key 的
plain/ZIP 24/24 漏检，故 `S3-R001/R008/R009` 保持 `OPEN`，整体 verdict=`FAIL`。不得上传或进入
Publish。T014 已用 clause-aware presentation entity slots、151-negative/73-positive/41-exact-entity
durable Oracle 和独立冻结 `223/223 PASS` 修复 presentation 双向泛化；public-safety 也经独立
29-case/58-surface plain/ZIP 盲测通过。三项 finding 仅推进为 `FIXED_PENDING_REREVIEW`，不得由 Builder
关闭。T015 随后在 277-path/287-file 新双 digest subject 上独立重审并判定 `FAIL`：第八组
presentation blind set 在 source/release 两面仅 `66/100` binary、`62/100` strict；public-safety
新 48-case/96-surface set 仅 `78/96`，另有独立 Historical/Forward 与深层 ancestry 真 CLI 复现。
`S3-R001/R008/R009` 回到 `OPEN`，未新增独立 P1/P2。T016 已改用 bounded semantic slots，
把 durable presentation matrix 扩为 175 REJECT / 85 ACCEPT / 58 exact-entity witness；public-safety
现可拒绝 `locator/cursor/alias`、neutral-container 深层 ancestry 与 private-context 任意 UUID，
同时允许稳定的描述性 public research request reference。三项 finding 仅为
`FIXED_PENDING_REREVIEW`。T017 随后在 278-path/288-file 新双 digest subject 上独立重审并判定
`FAIL`：第九组 presentation blind set 仅 `67/100` binary、`62/100` strict；public-safety
72-case/144-surface set 仅 `67/72` / `134/144`，另一组结构层 probe 也有 12/24 surfaces 失败。
current-tree v23 live witness 又因 provider usage limit 未取得 exact return/host replay，故
`S3-R001/R002/R008/R009` 为 `OPEN`，`ACC-S3-002/006` FAIL、`ACC-S3-009=FAIL_EVIDENCE`。
唯一下一 Task 是 `BSS-S3-P3-T018 — Remediation 9`。当前未安装
Codex/Agents runtime，也未 merge PR。版本或状态判断必须先从仓根运行
`python3 -B Stock_Skill/scripts/validate_registry.py`；任何冲突都降级为 `UNKNOWN`。

## 适用用户与决策

主要用户是使用 Codex 研究公开市场瓶颈、资格认证周期、产能短缺、生态系统约束和 theme-to-ticker 传导的研究者。
本 Skill 支持五种模式：

- `scan`：从 funded demand 建图并排序可投资角色；
- `deep_dive`：承销一个候选；
- `compare`：比较同一或相邻节点候选；
- `monitor`：追加证据、时钟、催化剂和 kill-switch 状态；
- `postmortem`：区分 thesis 质量、时点、beta、sizing 与运气。

它不用于简单查价、普通财报摘要、纯技术分析、交易执行、无证据荐股或保证收益。

## 不可互相补分的四道门

1. **约束真实**：功能必要、当前稀缺、难替代且扩张慢。
2. **稀缺持续**：约束持续时间足以覆盖公司兑现，不先被扩产、替代、政策或需求破坏解决。
3. **股东租金捕获**：正确上市实体拥有实质敞口，并在产能、合同、capex、融资、税和稀释后形成每股价值。
4. **预期差**：base case 尚未被估值、预期、持仓或拥挤度充分反映。

任一道失败都不能由其他高分补偿。Skill 还强制分离物理稀缺、公司兑现、市场发现三个时钟，执行负向搜索、
资本周期与最强反例，按共同根因而不是 ticker 数量计算组合集中，并保留 append-only 历史快照。

## 默认研究合同

缺少可选偏好时，默认全球流动性上市权益/公开代理、12–36 个月、long-biased evidence-first research、无杠杆、
无衍生品、无自动交易。只有司法辖区、禁止工具、损失承受能力等足以反转决策的缺失约束才阻塞。

所有研究必须明确 `as_of`、source cutoff、universe、horizon、liquidity floor、benchmark、risk budget、禁止工具
和预期 artifacts。历史研究拒绝 cutoff 之后的信息；实时研究必须刷新易变事实。

## 输入与输出接口

最小输入合同：

```json
{
  "schema_version": "1.0",
  "skill_version": "0.0.0.1",
  "request_id": "uuid",
  "query": "研究问题",
  "as_of": "YYYY-MM-DD",
  "source_cutoff": "YYYY-MM-DD",
  "previous_version": null,
  "mode": "scan|deep_dive|compare|monitor|postmortem",
  "universe": {
    "markets": ["US", "AU", "HK"],
    "asset_types": ["equity", "ETF"],
    "min_daily_value_traded_usd": 5000000
  },
  "horizon_months": 24,
  "risk_constraints": {
    "max_position_weight": 0.10,
    "max_root_driver_weight": 0.30,
    "leverage_allowed": false,
    "derivatives_allowed": false
  },
  "upstream_artifacts": []
}
```

Completion payload 使用独立的 Skill artifact schema `1.0`，不要与 registry schema `1.1` 混淆：

```json
{
  "event_type": "bottleneck_serenity_skill.thesis.completed",
  "schema_version": "1.0",
  "skill_version": "0.0.0.1",
  "request_id": "uuid",
  "thesis_id": "string",
  "as_of": "YYYY-MM-DD",
  "source_cutoff": "YYYY-MM-DD",
  "previous_version": null,
  "decision_file": "decision.json",
  "memo_file": "memo.md",
  "evidence_file": "evidence.json",
  "status": "complete|blocked|partial"
}
```

精确 schema、默认值与 adapter 合同见 `task-pack/02_ARCHITECTURE_DATA_API.md` 和 canonical
`references/integration_contract.md`。上游数据、估值、组合与监控适配器都是可选的；缺少它们时 Skill 必须仍可独立使用。

## 当前目录

```text
Stock_Skill/bottleneck-serenity-skill/
├── AGENTS.md
├── README.md
├── VERSION
├── CHANGELOG.md
├── SOURCE_INVENTORY.md
├── LICENSE_AND_ATTRIBUTION.md
├── LICENSE_SIMILARITY_AUDIT.json
├── RESTORE_AND_VERIFY.md
├── BACKUP_MANIFEST.sha256
├── scripts/
│   ├── audit_license_similarity.py
│   ├── build_release.py
│   └── refresh_task_manifest.py
├── releases/
│   ├── SHA256SUMS
│   └── bottleneck-serenity-skill_codex-skill-task-pack_v0.0.0.1.zip
└── task-pack/skill_draft/bottleneck-serenity-skill/
```

Release 只由封印的 `task-pack/` 确定性构建；真实 SHA 只在 `releases/SHA256SUMS`、registry 和 backup manifest
release entry 三处持久化。首版没有历史版本，因此不存在 `archives/` 目录。

## Source-only 验证

从 MetaDatabase 仓根运行：

```bash
python3 -B Stock_Skill/scripts/validate_registry.py
python3 -B Stock_Skill/bottleneck-serenity-skill/scripts/audit_license_similarity.py --verify-targets

SKILL=Stock_Skill/bottleneck-serenity-skill/task-pack/skill_draft/bottleneck-serenity-skill
python3 -B "$SKILL/scripts/validate_skill.py" "$SKILL"
python3 -B "$SKILL/scripts/validate_trigger_evals.py"
python3 -B "$SKILL/scripts/validate_security_evals.py"
python3 -B "$SKILL/scripts/validate_historical_e2e.py"
python3 -B "$SKILL/scripts/validate_forward_test.py"
python3 -B -m unittest discover -s "$SKILL/tests" -p 'test_*.py' -v

cd Stock_Skill/bottleneck-serenity-skill
python3 -B scripts/refresh_task_manifest.py --check
python3 -B scripts/build_release.py
python3 -B scripts/build_release.py --verify
```

第一条必须同时确认两个 active Skill；第二条从 canonical tree 动态推导 target 集合，并把当前
<!-- CURRENT_LICENSE_TARGET_COUNT=280 -->
`280`-file 审计报告绑定到该集合及冻结算法/上游 metadata；manifest `--check` 只读验证 task-pack file set，
builder 默认重建相同 release，`--verify` 校验 ZIP、两个 manifest、三方 SHA 与 registry。
完整来源、许可和恢复证据分别见 `SOURCE_INVENTORY.md`、
`LICENSE_AND_ATTRIBUTION.md` 与 `RESTORE_AND_VERIFY.md`。

## 安全与维护

- 研究与教育用途；不访问券商、不下单、不保证收益，也不替代法律、税务或持牌财务意见。
- 市场数据、filing 与 thesis 会衰减；每个结论都必须保存来源、日期、独立来源组和反证。
- 所有示例实体与数字均为合成数据，不能作为 live evidence。
- Owner：`LinzeColin/MetaDatabase` 维护者；版本、迁移和执行真源依次为 registry、项目/Task Pack `VERSION`、
  `SOURCE_INVENTORY.md` 与 `task-pack/00_RUN_CONTRACT.md`。
