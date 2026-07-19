# 目标架构

## 1. 产品边界

`stock-commercial-opportunities` 是无持久状态、无账户连接、无市场数据依赖的 Codex research-triage Skill。它定义证据链、研究状态和下一门禁；真实 filings/market/consensus/model provider 是可选下游，不随包安装。

```text
Mandate / universe / as-of
        ↓
Commercial mechanism + value chain
        ↓
Issuer/security normalization
        ↓
Source register ↔ atomic claim register
        ↓
Exposure attribution → financial capture
        ↓
Expectations / valuation / catalyst / falsifier
        ↓
score + risk + confidence + E0-E5
        ↓
research-only status + one diligence workflow
```

任一箭头断裂就降级，不由 LLM 叙事补齐。

## 2. 目录

```text
skill_draft/stock-commercial-opportunities/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── workflow.md
│   ├── commercial-mechanism.md
│   ├── evidence-protocol.md
│   ├── scoring-and-maturity.md
│   ├── diligence-gates.md
│   ├── output-contracts.md
│   ├── safety-and-boundaries.md
│   ├── stock-research-routing.md
│   └── evaluation.md
├── assets/
├── scripts/
├── evals/
└── tests/
```

`SKILL.md` 负责触发、顺序和硬不变量；细节在一层 references；确定性逻辑只在 scripts；assets 是输入/输出合同；evals 与 tests 分开语义和机械验证。

## 3. 核心对象

### Source

`id, title, url/locator, source_type, origin, access_level, evidence_class, issuer, period, retrieved_at, currency_unit, redacted`。

### Claim

`id, atomic statement, type, importance, topic, issuer, period, freshness, confidence, source_ids, supports/challenges`。

### Candidate

`security identity, beneficiary_path, exposure_proof, score/risk/confidence, E-level, status, claim_ids, assumption_ids, falsifiers, first_rejection`。

### Assumption

`candidate_id, category, statement, impact, uncertainty, status, source_ids`。

### Diligence

一个 critical claim，预注册 source/field/period/denominator/timestamp、pass/fail/inconclusive、cap、owner、review date 与 MNPI/license boundary。

### Decision

选中 candidate 或 `NONE`，声明 outcome/E-level、why not stronger、first rejection、rank-changing evidence 和一个 next workflow。

所有引用使用 ID；URL 只能出现在 Source allowlist。

## 4. 四个独立平面

| 平面 | 输出 | 不得替代 |
|---|---|---|
| Commercial | value pool、bottleneck、beneficiary pathway | issuer exposure |
| Issuer | identity、product/segment/geography、denominator | attractive equity setup |
| Equity | expectations、valuation、catalyst、downside、liquidity | personal trade decision |
| Evidence | confidence、E0–E5、freshness、conflicts | score |

## 5. 任务颗粒度

每个工作单元最多改变一条关键关系：

1. identity resolution；
2. one source open/register；
3. one atomic claim extraction；
4. one exposure denominator check；
5. one capture bridge；
6. one current expectations/valuation observation；
7. one catalyst/falsifier；
8. deterministic rescore；
9. one next diligence card；
10. synthesis/decision。

这让并行只用于真正独立来源/候选；最终由一个 writer 合并，避免多 Agent 重复搜索和冲突。

## 6. 性能设计

- SCREEN：最多 8 候选，3–6 source families；先 identity/exposure reject。
- ATTRIBUTE：最多 3 候选；优先 filing/segment denominator/capture。
- UNDERWRITE：只处理 E3+ survivors；补 current provider/timestamp、valuation、catalyst、downside。
- 连续两轮边际决定性信息 <10%、source/time/data cap 达到、或下一来源不会改变状态即停。
- 大文件先 locator/target section；不把全文塞进上下文。
- 默认单 writer；无明确授权不多 Agent。

## 7. 确定性与语义分工

脚本负责：字段/范围、加权计算、maturity derivation、status hard gates、ID/URL 关系、public/private、guarantee/personal-action/secret/local-path 扫描、package structure。

模型负责：商业机制、claim 原子化、来源解释、冲突、countercase、what-is-priced-in 假设和 next diligence。脚本通过不证明真实世界事实正确；语义评估仍需独立 A/B。

## 8. 安全/许可平面

- Public plane：代码、schema、synthetic fixtures、最小公开事实/链接、aggregated/redacted evidence。
- Private plane：portfolio/account/transaction/internal research/paid data/user material；不进入公开包。
- MNPI plane：疑似即停止并隔离，不参与结论。
- Provider plane：许可、timestamp、redistribution 与 access control 同次核验。

## 9. 可恢复而不安装

源码、测试、任务包、manifest 和 release ZIP 可从 MetaDatabase 独立恢复。恢复只运行目录内脚本，不写全局 Skill root、不创建 ticker memory、不连接服务。安装和语义发现始终是独立 Gate。
