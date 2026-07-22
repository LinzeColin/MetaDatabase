# bottleneck-serenity-skill

把公开市场投资主题转换为可审计、可证伪的瓶颈研究 thesis 的 source-only Codex Skill 项目。它先证明系统约束，
再检验稀缺持续时间、上市公司能否把租金转为完全稀释每股自由现金流，以及当前价格是否已反映该情景。

- Stable ID / invocation：`bottleneck-serenity-skill` / `$bottleneck-serenity-skill`
- Version：`0.0.0.1`；display/release label：`v0.0.0.1`
- Canonical Skill：`task-pack/skill_draft/bottleneck-serenity-skill/`
- Distribution：`SOURCE_ONLY`；local install：`PROHIBITED`
- Registry claim：`bottleneck-serenity-skill=0.0.0.1`
- 当前交付状态：`REGISTRY_ACTIVE / RELEASE_CANDIDATE_BUILT / STAGE_2_REVIEW_PASS / SOURCE_ONLY / NOT_INSTALLED`

当前工作树已用真实确定性 release SHA 激活 registry；这表示 source/release 可发现且可恢复，不表示已安装
Codex/Agents runtime。T005 已在新双 digest subject 上独立关闭机器接口 finding `S2-R001`；许可 finding
`S2-R002` 与 review ledger 25/25 均为 `CLOSED`，Stage 2 Review verdict=`PASS`。唯一下一 Task 是
`BSS-S2-P5-T001 — Publish`，它才会执行 staged/proposed-tree 封印、commit/push；当前候选尚未完成该
Publish。版本或状态判断必须先从仓根运行
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
│   └── build_release.py
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
python3 -B -m unittest discover -s "$SKILL/tests" -p 'test_*.py' -v

cd Stock_Skill/bottleneck-serenity-skill
python3 -B scripts/build_release.py
python3 -B scripts/build_release.py --verify
```

第一条必须同时确认两个 active Skill；第二条把审计报告绑定到 current canonical 的全部 39 个文件及冻结算法/
上游 metadata；builder 默认重建相同 release，`--verify` 校验 ZIP、两个 manifest、三方 SHA 与 registry。
完整来源、许可和恢复证据分别见 `SOURCE_INVENTORY.md`、
`LICENSE_AND_ATTRIBUTION.md` 与 `RESTORE_AND_VERIFY.md`。

## 安全与维护

- 研究与教育用途；不访问券商、不下单、不保证收益，也不替代法律、税务或持牌财务意见。
- 市场数据、filing 与 thesis 会衰减；每个结论都必须保存来源、日期、独立来源组和反证。
- 所有示例实体与数字均为合成数据，不能作为 live evidence。
- Owner：`LinzeColin/MetaDatabase` 维护者；版本、迁移和执行真源依次为 registry、项目/Task Pack `VERSION`、
  `SOURCE_INVENTORY.md` 与 `task-pack/00_RUN_CONTRACT.md`。
