# Run Contract 03 — `ADP-V12-S3-T001`

## Goal

在不部署、不改 Worker/cron、不引入 API key 或付费服务的前提下，为 `science-advances`
建立本地、可注入、失败关闭的 PubMed ESearch→EFetch 候选路径；它只返回现有 feed item
schema 与关联的 PMID/DOI provenance，不写 D1/R2，也不改变当前 Science.org RSS live 路由。

## Immutable Subject and Preconditions

- Subject 是 MetaDatabase 当前分支中的 `arxiv-daily-push/`；禁止恢复 CodexProject 旧源。
- `ADP-V12-S0-T001`、`S1-T001`、`S2-T001` 必须保持已验收状态；live 产品仍为 `0.41.0`。
- live `worker_cloud.js`、三个 cron、D1/R2、来源启停状态和 Cloudflare 资源均为只读基线。
- NLM Catalog 将 Science Advances 标识为 NLM ID `101653440`、电子 ISSN `2375-2548`、
  NLM 缩写 `Sci Adv`，并显示 PubMed 自 2015 年收录：
  <https://www.ncbi.nlm.nih.gov/nlmcatalog/101653440>。
- NCBI E-utilities 的 canonical base、ESearch→EFetch 管线、`tool`/`email` 使用规则与无 key
  速率边界以官方帮助为准：<https://www.ncbi.nlm.nih.gov/books/NBK25497/>、
  <https://www.ncbi.nlm.nih.gov/books/NBK25499/>。本合同采用更严格的 `<=1 req/s`。
- `tool=adp_cloud`，`email` 使用公开的项目联系邮箱。代码中存在这两个参数不等于已完成
  NCBI 注册；任何未来 live 接线必须另行证明注册/运营前置条件，本轮不得预签。

## Minimum Scope

- 一个 Science Advances/PubMed candidate-only 模块：URL 构造、ESearch/EFetch fetch、XML
  解析、期刊/日期校验、PMID/DOI 去重与结构化结果；fetch/clock/sleeper 可注入。
- 有界 XML fixtures、真实实现路径测试、一个只读可执行验证入口。
- 候选 registry、来源/用户中心/Owner 页面、双平面事实和 canonical HANDOFF 的必要同步。
- 来源专项门、任务包门、迁移治理门、安全门和 full-suite 精确问题集差分。

## Non-goals

- 不处理中文内容、移动端、视觉、版本、SLO 或部署；不进入 S4。
- 不导入 candidate 到 `worker_cloud.js`，不替换 Science.org RSS，不修改 cron、D1/R2 schema、
  生产数据、来源启停或 Cloudflare 资源。
- 不使用 API key、付费 API、代理、镜像、浏览器绕过、PDF/全文下载或 Entrez bulk dump。
- 不做 ESearch 分页、History/EPost、并发 E-utilities 请求或自动重试；429/HTTP error 失败关闭。

## Request, Rate and Cost Contract

- ESearch 固定 `db=pubmed`、`term=\"Science Advances\"[jour]`、`datetype=pdat`、
  `mindate/maxdate`、`retmode=xml`、`retmax=20`、`tool=adp_cloud`、项目公共 `email`。
- 日期输入是合法 `YYYY-MM-DD` 的 UTC 日历日、起止包含且 `start<=end`，窗口最多 7 天。
- 空 IdList 只产生 1 个请求并返回 `ESEARCH_EMPTY`；非空时只追加 1 个 EFetch，请求中的
  PMID 数量 `<=20`，固定 `db=pubmed`、`retmode=xml`、`tool/email`，不分页、不下载全文。
- 两个外部请求的**开始时间**至少相隔 `1000ms`；clock/sleeper trace 必须可执行验证。
  clock 倒退、sleep 后仍未达到间隔、429 或任一 HTTP/fetch/body 错误均返回 reason-coded
  失败，不重试、不产生 item。
- 两个端点均使用 HTTPS、GET、15 秒 timeout、`redirect=manual`；ESearch/EFetch XML 分别
  限为 64 KiB/2 MiB。请求参数中禁止出现 `api_key`。
- candidate 最多 2 个外部 subrequest；未来若另有合同授权其替换当前 Science.org RSS
  单次路径，净增最多 1。与 S1 Google 候选同时投影时为 `35/50`，本轮实际 live 仍为 `32/50`。

## Parsing, Identity and Item Contract

- 解析器只接受结构完整、大小有界的 ESearch/EFetch XML；DTD/外部实体不被解析或展开。
- ESearch PMID 必须为十进制正整数且唯一；EFetch 必须完整、且只能返回请求过的 PMID。
- 每条记录必须同时匹配 NLM ID `101653440`、ISSN/ISSNLinking `2375-2548`，以及规范化
  标题 `Science advances` 或缩写 `Sci Adv`。任一错误期刊阻断整批，返回零 item。
- 发布日优先取完整 `ArticleDate`，其次取完整 `JournalIssue/PubDate`；只保留合同日期窗口内
  记录，窗口外记录留下计数。日期缺失/不可解析或过滤后为零均失败关闭，不猜日期。
- PMID 或规范化 DOI 重复、DOI 缺失、标题缺失、非请求 PMID、请求 PMID 缺失均阻断整批，
  不返回部分成功或重复 item。
- 每条成功记录包含精确的现有 feed item：
  `{guid,title,link,summary,published}`；`guid=pubmed:<PMID>`，`link` 为 HTTPS DOI URL，
  `published` 为 UTC ISO-8601，`summary` 为有界纯文本。
- provenance 与 item 一一关联，至少保留 `pmid`、规范化 `doi`、NLM ID、ISSN、期刊标题、
  ESearch/EFetch endpoint 标识和查询日期窗口；provenance 不冒充现有 D1 schema 字段。
- 所有失败结果均为 `items=[]`、`records=[]`、`write_allowed=false`、
  `persistence_action=NO_WRITE`，并包含稳定 stage/reason code 与 request trace。

## Deterministic Tests

- 正向：ESearch→等待/限流→EFetch；期刊与日期匹配；输出 feed item schema；PMID/DOI
  provenance、请求参数和 2 次 subrequest trace 完整。
- 空搜索：`ESEARCH_EMPTY`，不调用 EFetch。
- XML：ESearch 坏 XML、EFetch 坏 XML、超尺寸 XML 均失败关闭。
- 标识：重复 ESearch PMID、重复 EFetch PMID、重复 DOI、缺 DOI、额外/缺失 PMID 均零 item。
- 过滤：错误 NLM/ISSN/期刊、窗口外、缺失或非法日期均零 item；正向混合夹具只允许
  明确在窗口内的 Science Advances 记录。
- 远端：ESearch/EFetch 429、503、timeout/fetch error、body read error 均 reason-coded 且不重试。
- 速率/身份：开始时间差 `>=1000ms`；倒退 clock 与无效 sleeper 负控阻断；两请求均有
  `tool/email`、无 `api_key`；无分页、History/EPost、PDF/全文或超过 20 PMID 的调用。
- 测试必须执行真实 candidate 路径；源码字符串/正则只能作补充，不能单独证明行为。

## Validation

```bash
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest arxiv-daily-push/tests/test_science_advances_pubmed_candidate.py -q
node arxiv-daily-push/tools/verify_science_advances_pubmed_candidate.mjs
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest arxiv-daily-push/tests/test_security_boundary.py -q
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest arxiv-daily-push/tests/test_source_registry.py arxiv-daily-push/tests/test_user_center_candidate_pool.py arxiv-daily-push/tests/test_owner_controls.py -q
python3.12 arxiv-daily-push/docs/pursuing_goal/v1_2/tools/validate_package.py --repo-root .
python3.12 arxiv-daily-push/machine/tools/check_dual_plane_ci.py --root . --projects arxiv-daily-push --require-projects
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest discover -s tests/governance -p 'test_adp_*.py' -q
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest discover -s arxiv-daily-push/tests -q
```

full suite 按测试名称集合与 S2 封存基线比较，candidate-only failure/error 必须为零；
`git diff origin/main -- arxiv-daily-push/deploy/cloudflare/worker_cloud.js` 必须为空。30 个 bundle、
424 个 manifests、前端原始归档和 CodexProject 旧源缺席状态必须保持不变。

## Risks, Rollback and Stop

- 风险：自制 XML 解析误收、期刊同名碰撞、日期猜测、重复标识产生双 item、限流时钟失效、
  联系身份被错误写成已注册、候选被误接 live。
- 回滚：删除 candidate-only 模块/fixtures/tests/registry 登记与本轮同步；不依赖数据迁移，
  live `0.41.0` 与 Science.org RSS 保持不变。
- 停止：`api_key_or_paid_service_required`、`journal_identity_cannot_be_proven`、需要 live/cron/
  schema/部署才能继续、NCBI 身份参数无法来自公开项目配置、负控未阻断、出现新增
  P0/P1/UNKNOWN/BLOCKED，或同一路径连续失败两次。
