# Run Contract 04 — `ADP-V12-S4-T001`

## Goal

在不调用模型、不声称翻译成功、不部署的前提下，关闭真实英文论文条目把英文摘要冒充为
“人话版”的缺陷：页面必须给出清晰中文结构，逐项区分已知、推断和未知；当没有可靠中文
解释时，统一诚实失败关闭，英文标题与摘要只出现在清晰标识、默认折叠的原文区域。

## Immutable Subject and Preconditions

- Subject 是 MetaDatabase 当前分支中的 `arxiv-daily-push/`；禁止恢复 CodexProject 旧源。
- `ADP-V12-S0-T001` 至 `ADP-V12-S3-T001` 必须保持已验收；当前 live 产品仍为
  `0.41.0` / build `c2ccc1fd01ec`，本轮不得部署或改变线上状态。
- canonical `worker_cloud.js` 是封存 production Subject，必须与最新 V0.2 production bundle
  保持逐字一致。本轮实现只以可确定性应用的 v1.2 candidate patch 存在；S6 集成前不得把
  candidate 写回 canonical Worker 或伪改 production bundle。
- 权威 Oracle 是 `ACC-V12-S4-001..002`；本合同只处理 `ADP-V12-S4-T001`，不得顺带处理
  S4.2 移动导航、S4.3 视觉/动效、版本、SLO、运维或发布。
- 当前 Worker 没有受信任的中文翻译/解释模型或带 provenance 的中文内容字段。因此真实英文
  条目在本轮只能进入诚实回退；不得把模板改写、关键词替换或现有英文句子称作翻译。

## Minimum Scope

- 以 canonical `worker_cloud.js` 为只读 base 建立可确定性物化的 S4.1 candidate patch；物化后
  的完整 Worker 由 item、review 和新生成讲义共用人话内容契约，保持现有八段讲义外形和旧
  中文内容路径可用。
- 对英文主导的标题/摘要生成中文 fail-closed 讲义：至少显式呈现“已知”“推断”“未知”三种
  状态和原文入口，且论文的方法、结果、因果、创新、局限等未被中文证据核实时一律标为未知。
- 详情/复习链路不得继续展示旧存储讲义中的英文模板或无 provenance 的中文论文结论；英文
  标题、作者、类目和摘要集中到有中文标签、无 `open` 属性的 `<details>` 原文区。
- 有界真实英文论文夹具、强制无模型夹具、旧存储讲义夹具、unsupported-claim 破坏负控、
  默认折叠破坏负控，以及可复跑的真实实现路径验证入口。
- 任务包、必要治理测试、阶段记录/HANDOFF 与双平面状态只在独立验收后同步；本阶段完成前
  只保留本地提交，不上传 GitHub。

## Non-goals

- 不接 OpenAI、第三方翻译、浏览器翻译、词典、模型权重、付费 API、API key 或外部网络。
- 不生成或推断论文的中文标题、研究问题、方法、结果、数字、因果、创新、边界或结论。
- 不修改 canonical `worker_cloud.js`、production bundle、来源/板块、registry、cron、D1/R2
  schema/数据、选择排序、FSRS、Cloudflare 资源或 live。
- 不做 S4.2 的四标签导航，不做 S4.3 的主题、视频、动效或像素门，不改产品版本。
- 不以静态字符串、builder 自报或单张截图独立证明验收；必须执行发货实现并有能阻断旧行为的
  负控。

## Content Contract

- **英文判定**：对标题与摘要做确定性脚本统计；存在足量拉丁字母且拉丁字母显著多于汉字时
  进入 `ENGLISH_SOURCE_NO_RELIABLE_ZH`。无摘要但英文标题明显时仍进入该状态；判定必须有界。
- **已知**：只允许复述 item 已有且不解释论文内容的事实，例如来源板块、发布日期、存在原文
  链接；每句带机器可检查的 `KNOWN` 状态和 locator。
- **推断**：在无可靠中文解释时固定为“未生成”，不得出现论文特定断言；状态为 `INFERENCE`。
- **未知**：研究问题、方法、结果、数字、创新、局限与结论均明确未核实，状态为 `UNKNOWN`。
- **原文**：英文标题/作者/类目/摘要只进入 `<details>`，`<summary>` 用中文说明，元素不得有
  `open`；原文链接在折叠区外可以保留，但不得把链接文案或标题称作中文解释。
- **可见英文上限**：真实英文验收夹具在折叠区之外不得出现原始标题/摘要，也不得出现连续
  8 个或以上英文单词构成的未解释正文；短分类码、URL 主机和 build id 不视为解释正文。
- **旧存储防线**：若英文 item 已有旧 `cn_lessons` 行，渲染必须忽略其中的原始英文和无来源
  中文 claim，重建本合同回退；不要求改写或删除数据库行。
- **中文路径**：非英文主导内容可继续使用既有确定性八段逻辑；旧句子缺状态时渲染为“推断”，
  不能升级成已知事实。

## Deterministic Tests and Negative Controls

- `TST-V12-HUMAN-LANGUAGE-REAL-ENGLISH`：真实英文论文 fixture 运行发货的 builder + renderer，
  断言八段非空、已知/推断/未知与原文入口齐全、折叠外无原始标题/摘要或大段未解释英文。
- `TST-V12-HUMAN-LANGUAGE-FAIL-CLOSED`：不提供任何模型/翻译能力，并注入含英文原句和伪造
  中文结论的旧存储讲义；发货渲染必须丢弃它，只显示诚实中文回退。
- 浏览器证据加载实际渲染 HTML，记录可见文本、`details.open === false`、三类状态标签和原文
  区文本；浏览器不可用时为 `UNKNOWN`，不能用源码字符串替代。
- 负控至少逐一证明以下旧/破坏行为会被检测器阻断：英文摘要直接进入“人话版”、旧存储伪造
  claim 泄漏、去掉 `<details>`/增加 `open`、去掉任一状态、把“推断未生成”改成论文断言。
- 保持现有 lesson dedup、de-math、任意板块非空讲义门可复跑；新增测试不得只检查复制实现。
- candidate patch 必须无 fuzz 地应用到封存 live Worker；验证器必须执行物化后的完整
  `default.fetch -> /item/:id`、`/today`、`/review` 路由，其中 `/today` 强制无存储讲义，
  并证明 canonical Worker/hash 与 production bundle 未移动。

## Validation

```bash
node arxiv-daily-push/tools/verify_human_language_fail_closed.mjs
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest tests/governance/test_adp_human_language_fail_closed.py -q
node arxiv-daily-push/tools/verify_lesson_dedup.mjs
node arxiv-daily-push/tools/verify_lesson_demath.mjs
node arxiv-daily-push/tools/verify_item_lesson_fallback.mjs
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest tests/governance/test_adp_lesson_dedup.py tests/governance/test_adp_lesson_demath.py tests/governance/test_adp_item_lesson_fallback.py tests/governance/test_adp_worker_build_stamp.py -q
python3.12 arxiv-daily-push/docs/pursuing_goal/v1_2/tools/validate_package.py --repo-root .
python3.12 arxiv-daily-push/machine/tools/check_dual_plane_ci.py --root . --projects arxiv-daily-push --require-projects
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest discover -s tests/governance -p 'test_adp_*.py' -q
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest discover -s arxiv-daily-push/tests -q
git diff --exit-code origin/main -- arxiv-daily-push/deploy/cloudflare/worker_cloud.js
```

full suite 按测试名称集合与 S3 封存基线比较，candidate-only failure/error 必须为空；根历史
`2 failures + 11 errors` 不得包装成绿色或通过恢复被禁止的旧根文档消除。S4.1 完成后仍不部署、
不上传，等待 S4.2、S4.3 和整阶段独立复审。

## Risks, Rollback and Stop

- 风险：语言判定漏掉英文、折叠区外残留标题/摘要、旧存储讲义绕过、把 metadata 扩写成论文
  结论、状态标签与真实语义不一致、过度过滤中文条目、candidate patch 随 base 漂移或物化后
  build stamp 失真。
- 回滚：删除本轮 candidate patch、验证器、测试及合同状态；canonical Worker、schema、数据和
  production bundle 均未修改，live `0.41.0` 保持不变。
- 停止：出现 `unsupported_translation_claim`、`raw_english_presented_as_chinese_explanation`、
  需要模型/API key/付费/联网/部署才能继续、浏览器证据不可获得、负控不阻断、英文旧存储仍
  可泄漏、出现新增 P0/P1/UNKNOWN/BLOCKED，或同一路径连续失败两次。
