# 证据卡起草通用说明（所有起草人必读）

（起草说明，可直接交给 Sonnet 起草人；起草人只写草稿目录里的 <卡id>.yaml）
你在为 Signal-Lattice（美股中小盘研究系统）起草「产业瓶颈证据卡」。一张卡 = 一个产业瓶颈，里面的每个评分都必须
由你**亲手打开过**的一手来源原文支撑。卡片会被程序逐字核验；编造、凭记忆写的摘录、没打开过的链接都会被核验脚本抓出来并作废。
宁可少写一个因子，也不要写一个撑不住的因子。

## 工作目录与工具（在仓库 Signal-Lattice/ 下，Python ≥3.11，PDF 需要 `pip install pypdf`）
- 下载并转文本，可选按正则打印上下文（PDF 自动转文本；SEC 链接自动带合规 User-Agent 和限速）：
    PYTHONPATH=src python3 scripts/card_getdoc.py "<URL>" "<正则1>" "<正则2>"      # 文本缓存在系统临时目录 signal-lattice-card-docs/，用完删掉，不进仓库
  状态码不是 200 就说明这个链接不能用。
- 找文档可以用 WebSearch / WebFetch（限制到一手域名）。**搜索摘要、小模型转述都不是证据**：只有你用 card_getdoc.py 拿到的原文里的句子才能当摘录。先定位文档，再打开、读原文、复制原句。
- SEC 公司申报列表：`https://data.sec.gov/submissions/CIK<10位补零CIK>.json`（用 card_getdoc.py 下载后读 JSON，找最新 10-K/10-Q 的 accessionNumber 与 primaryDocument）；
  申报原文链接格式：`https://www.sec.gov/Archives/edgar/data/<CIK无补零>/<accession去掉连字符>/<primaryDocument>`。
- 校验（草稿先放在 src/signal_lattice/evidence_cards/ 之外的任意目录，例如 /tmp/cards-draft/，通过后再拷进发布目录并重跑一遍）：
    PYTHONPATH=src python3 scripts/verify_evidence_cards.py --dir <目录>     # 逐个打开链接、核对摘录，写 <目录>/verification.json
    PYTHONPATH=src python3 scripts/card_check.py <目录>                       # 结构校验 + 印章校验，必须全部 OK
  核验脚本对摘录做「只比字母数字」的匹配，所以摘录必须是原文的连续片段（标点、断行差异不要紧，增删词不行）。

## 卡片格式（YAML 子集；所有字符串一律双引号；缩进 2 空格；不要用制表符；不要用单引号、多行块、锚点）
```yaml
schema: "signal-lattice-evidence-card/1"
id: "<卡id>"                       # 小写英文/数字/连字符，必须等于文件名
bottleneck: "一两句话：哪个产业的哪个环节是瓶颈，为什么。"
retrieved: "2026-10-01"
valid_until: "2027-09-30"          # 整张卡的有效期
factors:
  current_tightness:               # 因子名见下
    rating: 3                      # 0-5 整数
    valid_until: "2027-03-31"      # 可选；current_tightness 与 funded_demand 必须写，且不得晚于 2027-03-31
    basis: "一两句话：为什么是这个分，证据的局限是什么。"
    sources:
      - url: "https://www.energy.gov/....pdf"
        kind: "regulator"          # regulator | government_statistics | company_filing | industry_association | academic_paper
        publisher: "U.S. Department of Energy"
        title: "文档标题"
        excerpt: "原文摘录，最多 2 句、最多 600 字，必须是你打开的那份文档里的连续原文。"
companies:
  - cik: 1334933
    symbol: "UEC"
    name: "Uranium Energy Corp"
    market_cap_usd: 4693186778     # 由调用方给定，照抄
    market_cap_as_of: "2026-09-29" # 由调用方给定，照抄
    exposure: "一句话：这家公司在这条瓶颈里做什么（供给方/使用方/设备商），不是「受益」之类的判断。"
    source:                        # 必须是这家公司自己的 SEC 申报原文（sec.gov/Archives/...），摘录能证明上面 exposure
      url: "https://www.sec.gov/Archives/edgar/data/1334933/000143774926031414/xxxx.htm"
      kind: "company_filing"
      publisher: "U.S. SEC (company filing)"
      title: "Uranium Energy Corp Form 10-K FY2026"
      excerpt: "..."
contradictions:                    # 反证记录，至少 2 条：你**真的去找过**的反面证据
  - searched: "搜了什么（例如：有没有官方数据显示交期在缩短/新产能已投产/需求下滑）"
    found: "结果（没找到也要写：查了哪些来源、没有发现）"
    effect: "对评分的影响（例如：无，评分不变 / 因此把 current_tightness 从 4 降到 3）"
    url: "可选，一手来源链接，也会被打开核验"
```
因子名（只能用这八个；每个因子 0-5 分，分高 = 这一维的「结构性约束」更强、更持久）：
- funded_demand：对瓶颈产出的需求有没有真金白银锁定（合同、拨款、已批准的资本开支、长期购销协议），带数字越好。
- current_tightness：此刻供给是否真的紧（交期、短缺清单数量、产能利用率、价格、配给）。只认近期（≤ 18 个月）数据。
- supplier_concentration：合格供给方是否很少（前几家占比、单一国家占比、唯一来源）。
- qualification_barrier：新供给方进入要过多久/多难的资格门槛（监管批准、客户认证、许可、安全审查），有月/年数最好。
- substitution_difficulty：能不能用别的材料/技术/路线替代（官方资料里写明无替代品或替代需重新设计）。
- expansion_lead_time：扩产要多久（新厂/新矿/新产线从决策到出货的月/年数，含审批与设备交期）。
- policy_resilience：约束是否经得起政策/地缘变化而持续（政策本身制造或维持稀缺、供给地理集中且短期无法分散）；没有直接一手证据就不要写。
- architectural_necessity：下游系统架构上是否非它不可（设计标准/规范要求使用）；没有直接一手证据就不要写。

评分尺（scoring_model.md）：0 = 已被证伪或不存在；1 = 只有叙事；2 = 有道理但核验有限；3 = 可信且部分量化；4 = 强证据；5 = 多个独立来源、当前数字证据。

## 硬规则（程序会校验，违反则整张卡作废）
1. 来源只能是：政府/监管机构（.gov/.mil、SEC）、政府实验室/高校（.edu）、学术论文（arxiv、doi、nature、science、ieee）、国际机构（iea.org、oecd-nea.org、iaea.org、europa.eu 等）、行业协会官方统计（semi.org、nema.org 等）。**新闻、博客、券商观点、咨询公司摘要、Wikipedia 一律不行**，它们最多帮你找到线索，线索要追到原始文档。
2. 每个因子至少 1 条来源；评分 ≥4 必须至少一条摘录含数字；评分 5 必须有两家不同发布方各自的来源。拿不准就给低一分。
3. 摘录 ≤2 句、≤600 字，必须是原文连续片段（程序用「字母数字序列」匹配）。不要意译、不要加省略号拼接、不要改数字。
4. 每个评分必须有「这条来源如何支撑这个分」的 basis，诚实写局限（例如数据是 2024 年的、只覆盖美国）。数据陈旧就降分；current_tightness 用 18 个月以前的数据最多给 2 分。
5. 公司只登记你确认的：你必须找到该公司自己最新 10-K（或最新 10-Q）里能证明它在这条瓶颈里做什么的原句。找不到就不要登记这家公司（告诉调用方即可），不要硬凑。
6. 卡片说的是「产业层面的瓶颈是否真实」，不是「这家公司是不是好股票」；不要写任何估值、买卖、收益判断。
7. 反证必须是真实搜索：写清搜了什么、在哪搜、结果；如果反证确实削弱了某个因子，就降低评分并在 effect 里写明。
8. 不写私人信息；不引用任何没有用 getdoc.py 成功打开（200）的链接。
9. 没有证据的因子直接不写进 factors——系统会自动把它当作 NO_EVIDENCE，这是正确的。不要为了「填满」而凑数。

## 交回给调用方的东西（≤ 400 字）
- 卡 id、文件路径；各因子评分与一句理由；登记了哪些公司、没能登记哪些公司及原因；
- check_card.py 与 verify 脚本的最终输出摘要（必须全部 OK）；
- 你对哪些评分没有把握、哪里证据偏弱（诚实写）。
