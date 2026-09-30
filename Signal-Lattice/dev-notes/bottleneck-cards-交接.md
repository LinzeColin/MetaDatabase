# 瓶颈分支一手证据卡：交接给云端（WIP）

分支 `cloud/sl-bottleneck-cards-261001`（从 main `2b754a61c` 拉出）。任务原文：给「结构性约束」里申报拿不到的八个因子
（funded_demand、current_tightness、supplier_concentration、qualification_barrier、substitution_difficulty、expansion_lead_time、
policy_resilience、architectural_necessity）建立可审计的证据卡机制并填入第一批真实卡片；门槛数字一个不动。

## 一、已完成 / 未完成

| 项 | 状态 |
|---|---|
| 卡片格式、解析、校验、读卡规则（`src/signal_lattice/evidence/cards.py`） | 已写；只跑过一次手工解析对拍（与 PyYAML 结果一致），**没有单元测试** |
| 核验脚本 `scripts/verify_evidence_cards.py`（逐个打开链接、核对状态码与摘录、写印章 `verification.json`） | 已写；**从未对真实链接跑过**（本轮只是空目录冒烟） |
| 起草辅助 `scripts/card_getdoc.py`（下载+PDF转文本+按正则取上下文）、`scripts/card_check.py`（结构+印章校验） | 已写，冒烟通过 |
| 接入瓶颈分支：`bottleneck.apply_cards`、`score_bottleneck(..., cards=)`、收据 `detail.evidence_cards`、`KIND_CARD` | 已接；既有 `test_bottleneck_branch / test_research_cycle / test_branch_support / test_hub_backtest` 共 93 条仍通过 |
| 证据卡随快照钉住：`build_body(evidence_cards=)`、`EvidenceSnapshot.evidence_cards()`、`research_cycle --evidence-cards DIR` | 已接 |
| `pyproject.toml` package-data 带上 `evidence_cards/*.yaml` 与 `verification.json` | 已改（未实际打 wheel 验证） |
| **第一批真实卡片（≥5 张、≥20 家公司）** | **0 张。没有写出任何卡片**；只完成了选题与公司名单（见第四节） |
| 新增单元测试（schema、过期失效、来源缺失退化、门槛未放宽、快照钉住、端到端） | 未写 |
| `重建/06_证据卡怎么做怎么续期.md` | 未写（本文件 + `bottleneck-cards-起草说明.md` 是素材） |
| `HANDOFF.md` 新条目 | 未写 |
| `signal-lattice research` 前后对比 | 未完成：基线那一次跑到候选池建好（1233 只）、正在做增量采集时被叫停，**没有 PASS 数**。HANDOFF 里 2026-09-30 的线上结果是瓶颈 0 PASS，可作为基线参照，但要在同一 as_of 重跑才算前后对比 |

## 二、设计（已实现的部分按这个走，改动请先想清楚）

1. **卡片放哪**：`src/signal_lattice/evidence_cards/<id>.yaml` + `verification.json`。没放在任务里举例的 `Signal-Lattice/evidence_cards/`，
   原因：生产机装的是离线构建的 wheel，`cli.project_root()` 在已安装环境里不是源码树（`research_cycle._event_atlas_params` 的注释也写了这一点），
   放源码树顶层的文件运行期读不到；放包内 + package-data 才会随 wheel 发布。
2. **YAML 零依赖**：`pyproject` 的 `dependencies = []`，wheel 是 `pip wheel --no-deps --no-index` 离线构建，不能引入 PyYAML。
   `cards.parse_simple_yaml` 是极小子集解析器（块映射/块列表/双引号字符串/整数/小数/布尔/null/`[]`/`{}`/注释，其余一律报错）。
   卡片里**所有字符串一律双引号**。本机有 PyYAML 时可用它对拍（写测试时做一条对拍用例，没装就 skip）。
3. **读卡规则**（`CardBook.for_company(cik, as_of)`）：整张卡结构不合格 → 作废；`as_of < retrieved`（时点正确）或 `as_of > valid_until` → 失效；
   每条来源必须有印章（`verification.json` 里 key = sha256(url + 规范化摘录)，状态码 200、摘录找到、核验日 ≤ as_of）；
   评分对来源的要求（≥4 要带数字摘录；5 要两家不同发布方）在**印章过滤之后**再判一次。任何一条不满足 → 该因子保持 NO_EVIDENCE（不填中值、不记 0）。
   多张卡给同一公司同一因子时取最低分（保守）。
4. **怎么填因子**（`bottleneck.apply_cards`）：只补「公司层面没有证据」的因子；公司自己的 XBRL/10-K 抽取已给分的因子不动，卡片只在收据里记一笔（评分差 ≥2 标 conflict）。
   填入的因子状态是 `PROXY`（行业层面证据套到这家公司），因此不进 `numerical_traceability` 的分母；来源 ref 的 `kind="card"`，
   不计入「SEC 原文链接」，所以 `no_primary_evidence` / `primary_source_coverage` 的判定不变。**不碰 `gates`、`coverage`、`param_floors`。**
   （备选：让卡片覆盖 funded_demand/current_tightness 里只有间接代理的公司层证据——更宽松、更难辩护，本轮没做，需要主线拍板。）
5. **为什么卡片要钉进快照**：分支在隔离子进程里只读快照；同一快照（hash 相同）必须得到同样的结果，所以卡片内容随 `build_body(evidence_cards=)` 进 hash。
   旧快照没有这一项 → `evidence_cards()` 返回 None → 等同没有卡片。回测 `hub_backtest` 仍走 `bottleneck_receipts(..., cards=None)`（历史 as_of 早于检索日，本来也用不上）。
6. **不要往 `DEFAULT_PARAMS` 加键**：`check_shape` 要求 `Stock_Skill/bottleneck-serenity-skill/runtime/params.json` 与默认值同构，加键会让线上参数校验失败。
   卡片校验口径（有效期上限 366/190 天、评分与来源数量的对应）是 `cards.py` 里的常量，不是门槛。

## 三、卡片格式（细则见 `bottleneck-cards-起草说明.md`，可直接当 Sonnet 起草人的指令）

顶层键固定：`schema, id, bottleneck, retrieved, valid_until, factors, companies, contradictions`。
- `factors.<因子>`：`rating`(0-5 整数)、`basis`、`sources[]`（`url/kind/publisher/title/excerpt`）、可选 `valid_until`；
  `current_tightness` 与 `funded_demand` 有效期不得超过检索日起 190 天，整张卡不得超过 366 天。
- `companies[]`：`cik/symbol/name/exposure/source/market_cap_usd/market_cap_as_of`；`source` 必须是该公司自己的 SEC Archives 申报原文 + 摘录；
  `market_cap_usd` 必须在 3–50 亿美元（取自候选池快照，见下）。
- `contradictions[]`：`searched/found/effect`（可选 `url`），至少一条，必须是真实搜索。
- 来源类别 `regulator | government_statistics | company_filing | industry_association | academic_paper`；域名白名单 `cards.PRIMARY_HOST_SUFFIXES`
  （.gov/.mil/.edu/sec.gov/arxiv/doi/europa.eu/iea/oecd-nea/iaea/…；新闻、博客、券商、咨询摘要不在其中）。
- 摘录 ≤2 句、≤600 字，核验脚本按「只比字母数字」匹配，必须是原文连续片段；WebSearch/WebFetch 的摘要不是证据，必须用 `card_getdoc.py` 亲手打开原文。

## 四、第一批选题与公司名单（候选池快照 2026-09-29，1233 只；市值区间 3–50 亿美元；数字现扫）

候选池快照已随本机临时目录删除；云端要重新生成（首次约 25–30 分钟，见第五节）。下面是我按名称/SIC 筛出的、市值在区间内的公司，**CIK 与市值来自那次快照，使用前请对新快照复核**
（Powell、Centrus、Preformed 以外的许多「典型」瓶颈公司这次都不在池内——市值已越出区间，别凭印象选）。

| 瓶颈（卡 id 建议） | 公司（代码 CIK 市值亿美元） | 一手来源线索（已用 WebSearch 定位，**尚未逐个打开核验**） |
|---|---|---|
| `nuclear-fuel-cycle` 核燃料（铀供给/转化/浓缩/HALEU） | UEC 1334933 46.9；UUUU 1385849 27.7；NNE 1923891 8.5；IMSR 2019804 4.1 | EIA《Uranium Marketing Annual Report》（2025 版 2026-08：美国电厂 2025 年铀交付中美国产仅 7%，浓缩服务美国来源 23%、俄罗斯 26%）`https://www.eia.gov/uranium/marketing/pdf/umar.pdf`；DOE HALEU 可得性资料；NRC |
| `grid-equipment` 电网设备与施工产能（变压器/变电/线路硬件） | PLPC 80035 19.9；MYRG 700923 45.6；PRIM 1361538 40.3；CTRI 1981599 20.3；ATKR 1666138 32.0；AMSC 880807 14.1；AZZ 8947 40.4 | DOE《Large Power Transformer Resilience Report to Congress》2024-07（已打开核对：原文「36-month lead times being commonly quoted and maximum lead times reaching as much as 60 months」；2019 年 >60MVA 新增约 750 台、超过 80% 进口；GOES 约 80% 进口）`https://www.energy.gov/sites/default/files/2024-10/EXEC-2022-001242%20-%20Large%20Power%20Transformer%20Resilience%20Report%20signed%20by%20Secretary%20Granholm%20on%207-10-24.pdf`；DOE OE 配电变压器工作组页面 `https://www.energy.gov/oe/distribution-transformers`；NREL `https://docs.nrel.gov/docs/fy24osti/87653.pdf`；GAO-23-106180。注意 2024 年数据对 current_tightness 偏旧（≤2 分），需找 2025–2026 的一手数据；公司层面 AZZ/ATKR 与变压器的关系偏弱，登记前必须在其 10-K 里找到原句 |
| `critical-minerals` 关键矿产（锑/稀土/铌钪/铜） | UAMY 101538 6.3；PPTA 1526243 27.0；UUUU（同上）；IDR 1030192 4.5；NB 1512228 5.3；TMC 1798562 17.0；TMQ 1543418 5.4；IE 1879016 16.0 | USGS《Mineral Commodity Summaries 2026》（进口依赖、主产国占比、替代品）；USGS 关键矿产清单；商务部 232 调查/联邦公报 |
| `sterile-injectables` 无菌注射剂与药品短缺 | AMPH 1297184 11.1；ANIP 1023024 16.3；ETON 1710340 14.5；PRGO 1585364 20.5；HROW 1360214 11.5 | FDA 药品短缺数据库与报告、HHS ASPE/ASPR 供应链报告；ASHP（行业协会官方统计）。登记前核对各公司 10-K 是否真做无菌注射/短缺品 |
| `munitions-missile-industrial-base` 弹药与导弹动力工业基础 | KRMN 2040127 43.4；DCO 30305 25.9；AADX 2118195 20.8；OLN 74303 17.7；RDW 1819810 26.2 | GAO 关于弹药/固体火箭发动机工业基础的报告；国防部工业基础政策办公室报告；陆军弹药产能公告。公司是否在该链条里，以其 10-K 原句为准 |

合计 5 张卡、约 28 个候选公司（去重后），够「≥5 张卡、≥20 家」，但每家必须先在自己的 10-K 里找到原句才能登记，找不到就剔除，别凑数。
评分取向：没证据的因子不写；current_tightness 用 >18 个月旧数据最多 2 分；单一来源的因子最高 3，4 分要数字摘录，5 分要两家不同发布方。

## 五、数据来源与抓取规则

- **SEC**：必须带 User-Agent。研究层读环境变量 `SIGNAL_LATTICE_SEC_UA`（本轮用 `SignalLattice research noreply@anthropic.com`；缺失直接报错退出，仓库不内置默认值）。
  研究层自带限速 ≤4 次/秒（任务要求 ≤10 次/秒）；`verify_evidence_cards.py` 对 sec.gov 请求间隔 ≥0.35 秒，其余站点 ≥0.6 秒（非 SEC 站点用浏览器 UA，否则部分 .gov 站点拒绝）。
- 候选池：新浪行情（`hq.sinajs.cn`，需 Referer）+ 腾讯日线 + SEC 股数；本机直连均可用（2026-10-01 实测 200）。
- 一手来源打开：`scripts/card_getdoc.py`；起草后 `verify_evidence_cards.py` 逐个开链接并记状态码（PR 里要列出每个链接的状态码）。
- 二手来源（新闻、博客、券商观点）只能当线索；AI 生成内容不算证据。

## 六、下一步具体做法

1. 环境：Python ≥3.11（本机默认 3.9 跑不了；我用 `uv venv --python 3.12 venv`，再 `uv pip install pytest setuptools pyyaml pip wheel pypdf`）。
   基线测试：`cd Signal-Lattice && PYTHONPATH=src python -m pytest -q -p no:cacheprovider tests`。
2. 选题与公司：先重新生成候选池（第 5 步的 research 命令首段会建），按第四节复核每家公司的 CIK 与市值，再定 5 张卡的公司名单。
3. 起草卡片：每张卡派一个 Sonnet 起草人（`model: sonnet`），指令用 `dev-notes/bottleneck-cards-起草说明.md` + 该卡的 id、公司表（含 `market_cap_usd`/`market_cap_as_of`）、线索来源；
   起草人只写草稿目录。**评分与入卡由主线亲自复核**：逐条读摘录是否真支撑该评分、有没有被反证削弱。
4. 落盘：草稿通过 `card_check.py` 后拷进 `src/signal_lattice/evidence_cards/`，在那里再跑一遍 `verify_evidence_cards.py`（生成最终 `verification.json`）与 `card_check.py`；
   把每个链接的状态码汇总进 PR 描述。卡片 `valid_until` 建议整卡 2027-09-30，current_tightness/funded_demand 2027-03-31。
5. 写测试 `tests/test_evidence_cards.py`：① YAML 子集解析对拍 PyYAML（没装就 skip）与非法写法报错；② schema 校验（非一手域名、摘录超 2 句、评分 4 无数字、评分 5 单一发布方、有效期超限、缺反证、公司市值出区间、id 与文件名不一致）；
   ③ 读卡规则（过期 → CARD_EXPIRED、早于检索日、无印章/状态码非 200/摘录没找到/改摘录后印章失配 → 因子仍是 NO_EVIDENCE，且不是 0 分）；
   ④ 接入（合成卡 + `branch_fixtures` 的公司：NE 因子被填且状态 PROXY、ref 的 kind 为 card；公司自己有证据的因子不被覆盖；过期后回到 NO_EVIDENCE）；
   ⑤ 门槛未放宽：`B.DEFAULT_PARAMS["gates"]`/`["coverage"]` 与现值逐项相等（对照 `ScoringModelPinnedTests`），`param_floors` 只许收紧；
   ⑥ 快照：`build_body(evidence_cards=...)` 进 hash、`EvidenceSnapshot.evidence_cards()` 取回、缺项返回 None；
   ⑦ 端到端：在 `test_research_cycle.py` 的合成世界里传 `CycleConfig.evidence_cards_dir`，断言瓶颈分支收据里出现 `evidence_cards.used`；
   ⑧ 随包卡片全部结构合格且每条来源（含公司申报）都有 200 + 摘录找到的印章（**不要**写「今天没过期」的断言，否则 CI 到期即红）。
6. 文档：在 `Signal-Lattice/重建/` 加 `06_证据卡怎么做怎么续期.md`（零上下文新 agent 能照做：选题→找一手来源→起草→核验→落盘→测试→续期：到期前重开每个链接、重抄摘录、更新 retrieved/valid_until、重跑核验）。HANDOFF.md 加一条。
7. 研究层前后对比：
   ```
   export SIGNAL_LATTICE_SEC_UA="SignalLattice research noreply@anthropic.com"
   cd Signal-Lattice
   PYTHONPATH=src python -c "import sys; from signal_lattice.cli import main; sys.exit(main(sys.argv[1:]))" research --work-dir <W> --out-dir <O> --evidence-cards <空目录>   # 基线：无卡片
   PYTHONPATH=src python -c "..." research --work-dir <W> --out-dir <O> --skip-collect                                                       # 带卡片（默认读包内目录）
   ```
   首次会建候选池（约 25–30 分钟，1233 只）并做 SEC 增量采集（数小时，90 分钟 systemd 超时只对线上适用；本机要自己设总量上限）。
   报告：瓶颈分支 PASS 数前后、每个 PASS 的 `detail.evidence_cards.used` 与 `detail.factors.constraint.*.refs` 证据链；若仍 0 PASS，报告卡在哪道门（`detail.gates`、`dimensions.constraint.reason`）。
   若云端访问 SEC 受限，写明并用单元测试证明机制。
8. 开 PR 到 main（不合并），描述写：链接状态码表、测试命令与结果、没做到的与原因。commit 末尾 `Co-Authored-By: Claude <noreply@anthropic.com>`，PR 末尾 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`。

## 七、踩过的坑

- 本机 macOS 上 `tests/test_branch_runner.py::...cannot_see_another_branchs_output...` 与 `tests/test_deployment_northstar.py::...rollback_console_paths...` 两条**在未改动的 main 上就失败**（`/var` → `/private/var` 符号链接路径比较、私有临时目录同级残留），Linux CI 上应通过；别当成自己的回归。
- macOS 没有 `timeout` 命令；长任务用 `perl -e 'alarm N; exec @ARGV'` 包一层，并在收工时亲手杀掉进程。
- 候选池首次构建要先逐只拉日线/申报画像，日志在结束前不输出；判断进度看 `<work>/universe-cache/bars` 的文件数（总数约 1400 只量级）。
- 公司层面的市值会大幅漂移：Powell、Centrus 等「教科书瓶颈公司」这次都已超出 50 亿上限，不在池内；名单必须以新快照为准。
- `WebSearch` 返回的摘要里夹带的数字不能直接用（它是模型转述）；必须打开原文。SEC 与 .gov 的 PDF 用 pypdf 抽文本，抽不出来的来源不能入卡。
- `check_shape` 对参数文件极严（见设计第 6 条）。`score_bottleneck` 的 `structure` 路径会提前 return，卡片只能在 `constraint_factors` 之后统一套（现在就是这样）。
