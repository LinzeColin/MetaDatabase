# EEI 生产金标标注协议（T904 / A026-A027）

版本：v1（2026-07-16）。授权依据：Owner 决策 D3（2026-07-15）——来源引证式标注全权委托接管代理执行，Owner 批次签核。

## 1. 采样框（sampling frame）

金标只来自**一手权威公开来源**，与被测系统输出完全独立（合成自评禁止）：

- NVIDIA FY2026 Form 10-K（SEC EDGAR 官方存档 HTML 与 investor.nvidia.com PDF 两种渲染）
- NVIDIA 官方 newsroom/blog 三篇（Taiwan ecosystem / AI factories / Computex 2025）
- ASML 官方 story（Busting ASML myths）
- TSMC Press Center 两篇（#1408、#1734）
- SEC EDGAR `company_tickers.json` 官方注册表（实体表面形与法定名）

语料以 SEC 合规 UA 实抓，全文存 `runtime_evidence/EEI/gold_corpus/`（不入 git），
逐源 sha256 记录于 `manifest-20260716.json`。构建器对每条正例锚句做**逐字 fail-closed
校验**（锚句不在源文即中止），并对语料哈希与 manifest 对拍。

## 2. 标签语义

- **实体解析例**：`input_text` 为源文/注册表中逐字出现的表面形；`expected_entity_id`
  为 140 家公司研究宇宙（`company_research_universe`）的 `research_id`；宇宙外真实
  公司为负例（expected 为空 = 正确行为是不解析）。
- **关系例**：`expected_relationship_key` 词表 = `subject_rid|relationship_type|object_rid`，
  类型取自 `relationship_type_catalog`（52 类）。**正例**必须有可引证锚句；**负例**语义为
  "该关系未被本采样框内任何来源断言"（frame 内断言缺失，非世界性否定），每条负例记录
  已核查的来源与理由（含方向反转、类型替换、对冲式披露三类系统性负例）。
- 对冲披露（如 10-K 中"正在敲定、无法保证完成"的 OpenAI 投资条款）标注为 `false`。

## 3. 预测侧（系统真实输出）

- 实体：`GET /v1/entities?q=<input_text>` 首位结果经 `entity_id`/法定名映射回
  `research_id`；无结果即空串。
- 关系：生产库 `relationships`（status=reported，即已发布断言）映射到 research_id 三元组；
  金标键在集合中即 predicted_present=true。
- 预测在标签冻结同时刻采集，绝不因金标调整。

## 4. 冻结与签核

- `label_freeze_sha256` = 实体+关系 case 数组的 canonical JSON sha256；冻结副本存
  `runtime_evidence/EEI/gold_corpus/label_freeze_20260716.json`。Owner 批次签核字段
  （`owner_batch_signoff`）在 evidence 块内，不参与冻结哈希——签核不可改动标签内容。
- 标注者：`claude-eei-takeover-agent-d3`（资质引证：MetaDatabase PR #2 ROOT_LOCK
  Owner 签认、PR #8 首次 Owner 签核发布）。Owner 批次签核后方可作为 A026/A027 关账证据。

## 5. 门槛与边界

- A026：≥50 例、precision ≥ 0.95、来源覆盖=1.0；A027：≥100 例、precision ≥ 0.90、
  覆盖=1.0。**recall 必须上报但不是关账门槛**（recall 提升属 S7PD 数据扩张线）。
- 金标通过只关 A026/A027，不触碰 A202/A209/A210/release-manager 任何门。

## 6. 校准回路（v1 附录，S7PCT02）

- 校准动作**永不改动金标**：预测刷新产生新数据集版本（v2、v3…），其 `gold_only_sha256`
  （去除 `predicted_*` 字段后的 canonical JSON sha256）必须与已签核版本逐字节一致，
  Owner 批次签核方可延续；任何金标内容变更都是新批次，需重新签核。
- 每轮校准记录 `t904_calibration_iteration_NNN_*.json`：诊断（FN 家族分析）→ 动作
  （引证官方数据/代码修复，fail-closed）→ 复测（before/after 全指标）→ 剩余缺口归属。
- 迭代 001（2026-07-16）：官方 ticker/CIK/注册表题名标识灌注（39 行，SEC 注册表哈希对拍）；
  A026 recall 58.5%→65.9%（precision 保持 1.000），解析机制从模糊匹配转为确定性
  identifier 命中；剩余 FN 全部为实体人口缺口（S7PD 范围）。
