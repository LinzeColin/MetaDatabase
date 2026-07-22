# License and attribution

Audit date：2026-07-23。本文记录 `bottleneck-serenity-skill` 的 proprietary 边界、输入来源、第三方来源、
复制/未复制决定和再分发结论；它不替代仓库根 `LICENSE`，也不扩大任何第三方许可。

## 项目许可

除下文明确标识的 MIT-covered portions 外，转换后的项目源码与文档受 MetaDatabase 根 `LICENSE` 约束：
Copyright (c) 2026 LinzeZhang，All Rights Reserved。未经版权人书面许可，不授予使用、复制、修改、发布、
分发、再许可或销售权。仓库公开可见不等于开源，也不构成任何默示许可。

本项目保存的是 source-only 备份，不是本机安装或交易系统。研究输出不保证收益，也不替代法律、税务或持牌
财务意见。

## 用户提供的输入包

用户明确要求把下列输入工程化并上传到其 MetaDatabase 项目；该指令是本次转换和仓内保存的授权依据。
输入文件本身不提交，只保留逻辑名、SHA-256、大小与迁移决定：

| Logical artifact | SHA-256 | 处置与再分发结论 |
|---|---|---|
| `input-archive.zip` | `541fce14f8eaa4b73a8c170fc6f6bc0f8cd5aa509942fe2192bd8cddafd90815` | 53-entry 迁移证据；不作为 current release 或 archive 提交。 |
| `outer-skill.md` | `69c78b85bd08695b6e1403d6b768be468277f845450c9f9736dba945a58058ba` | 与归档内 `SKILL.md` 相同；重构为 stable-ID 入口。 |
| `handoff.zh-CN.md` | `182270834e8618f2b5f5750265938a39bd91a20240885fcf6289cc9694239f8a` | 要求迁入 Task Pack，不逐字作为 Skill resource 发布。 |
| `quickstart.zh-CN.md` | `53a9c8cd9b44857df3f66d11f815b45c88a6db6fb6c0424092cab12e649c3462` | 仅迁移产品用法；本机安装命令明确排除。 |
| `research-report.zh-CN.md` | `0359125da22050fd0d7bd1f9b62abf646ef1d43de29121a851b185b3e5ee57f8` | 方法审计依据；不提交，历史结论不冒充本项目测试证据。 |

输入 ZIP 没有 `LICENSE` 或 `COPYING`。其 `PROVENANCE.md` 声明 scripts、schemas、scoring、templates 与 wording
为原创综合且未复制列出的 Serenity 仓库代码。本文保留该声明作为**源主张**，但最终再分发结论不只依赖它：
下文另行记录独立 upstream license 与完整历史相似性审计，并对可疑相似片段采取更保守的 MIT 归属。

源 ZIP 的全部 53 项、逐项 hash、唯一 `IMPORT/MIGRATE/EXCLUDE` 决定及目标归宿见 `SOURCE_INVENTORY.md`。
源 `VERSION=0.1.0` 已明确排除；它不是 current、archive 或可比较的版本谱系。

## Serenity 与公开实现

下表的 commit 是本次独立审计冻结点。`COPY DECISION` 描述本仓实际保留内容，而不是对上游整体版权状态的推断。

| 来源 | 审计 commit / license | 使用与复制决定 | 再分发结论 |
|---|---|---|---|
| Serenity on X，`@aleabitoreddit`，<https://x.com/aleabitoreddit> | 社交账号；无软件许可 | 仅作为方法身份与公开讨论来源引用；未收录 tweet、媒体、账户数据或业绩记录。 | 仅事实性引用；不再分发其内容，社交业绩声明不视为审计证据。 |
| `muxuuu/serenity-skill`，<https://github.com/muxuuu/serenity-skill> | `c2fe93deedfd0d1bd9fe7ef0601ea1b9c20ea24a`；MIT，Copyright (c) 2026 muxu | 审计其 workflow、additive scorecard 与 validator。没有整文件复制；目标 score CLI/output 与 frontmatter validator 出现有限连续相似片段。为避免依赖“独立创作”推断，相关 scaffolding 保守分类为 `POSSIBLE_ADAPTATION / MIT-COVERED`。 | MIT 允许保留与修改；本文件完整保留其 copyright 与 permission notice。其余项目仍为 proprietary。 |
| `yan-labs/serenity-aleabitoreddit`，<https://github.com/yan-labs/serenity-aleabitoreddit> | `3fe902b29aa7f32d8ab245c5b87b596cb4d85eb9`；仓库与完整历史未发现 LICENSE/COPYING，GitHub 为 `NOASSERTION` | 只用于理解 archive-derived 方法、风险与未审计业绩限制；未复制代码、tweet 数据、图片、分析文档或其他 payload。 | 仅名称/URL/思想层引用；禁止把其代码、数据或长段内容并入本项目，除非取得单独许可。 |
| `Mrjie7205/serenity-bottleneck-hunter`，<https://github.com/Mrjie7205/serenity-bottleneck-hunter> | `15bb654f41cb39f442ba2076b4023436a0d7554d`；MIT，Copyright (c) 2026 Mrjie7205 | 用于审计 constraint archetypes、ticker hygiene 与公开样本外 scorecard；未发现整文件、四行片段或实质代码复制。 | 事实与思想层引用；当前 payload 不复制其代码，因此不把其 MIT 代码混入本项目。 |
| `wesson9527/chokepoint-atlas`，<https://github.com/wesson9527/chokepoint-atlas> | `207bf340a86c0342b28934e578162610accefe73`；仓库与完整历史未发现 LICENSE/COPYING，GitHub 为 `NOASSERTION` | 只参考 graph/role 思维；未复制 code、images、docs、templates 或 examples。 | 仅名称/URL/思想层引用；无明确许可内容不得再分发。 |

### 独立相似性审计

可执行真源是 `scripts/audit_license_similarity.py`；确定性结果是 `LICENSE_SIMILARITY_AUDIT.json`。审计器
不联网、不记录 clone 路径或上游文本，要求调用者提供四个完整、非 shallow clone，并逐个验证 origin、冻结
commit 和 LICENSE/COPYING 历史。算法固定为：

1. target 是 canonical Skill 当前递归出现的全部 39 个普通文件；任一 symlink、非严格 UTF-8 或含 NUL 的
   target 直接失败，不允许静默缩小集合；
2. upstream 是每个冻结 commit 及全部 ancestors 可达的每个 unique Git blob，不按 path 或 size 排除；严格
   UTF-8 解码成功且原始 bytes 无 NUL 才计为 text blob；
3. exact match 是完整 raw payload SHA-256 相等；行匹配先按物理行 `splitlines`，逐行 Unicode NFC、去除首尾
   Unicode whitespace、把内部 whitespace run 折叠为一个 ASCII space，再比较四个物理连续且均非空的行；
4. pair 身份精确为 `target relative path + upstream repository + blob OID`，同一 pair 的多个 window 只计一个
   pair；`token20` 仅表示至少一个命中 window 含 20 个 ASCII `[A-Za-z0-9]+` token，是人工复核候选而非
   法律结论；报告只保存行号、window hash 和 token count。

最终两次完整重算得到 byte-identical 报告：39 个 target files 对四仓 2,489 个 reachable unique blob
instances，其中 2,485 个符合 text eligibility（muxuuu 34、yan-labs 2,265、Mrjie7205 139、wesson9527 47）；
四个被排除 blob 均含 NUL，没有依赖尺寸捷径。结果为 exact pairs=`0`、规范化四行 pairs=`3`、token20
pairs=`1`：

- muxuuu 的 `score_opportunity.py` pair 命中 7 个 window，其中 2 个达到 token20；
- muxuuu 的 `validate_skill.py` pair 命中 3 个 window，均低于 token20；
- wesson9527 的唯一 pair 是 `test_validate_evidence.py` 与一个历史 blob 的 2 个纯 JSON 闭合标点 window，
  token count 均为 `0`，不构成代码/文本复制证据；
- yan-labs 与 Mrjie7205 没有任何 exact 或四行 pair。两个无明确许可仓合计 exact=`0`、token20=`0`。

前两个 muxuuu scaffolding 继续按 `POSSIBLE_ADAPTATION / MIT-COVERED` 保守归属并保留完整 notice。该审计证明
当前 39-file payload 与冻结历史之间没有未声明的整文件复制，并把所有宽匹配显式留给人工判断；它不能替代
未来每次新增来源的许可审查。若 canonical file set/hash、上游冻结点、license 历史、算法或结果漂移，
`--verify-targets`/`--verify-report` 必须失败，release 状态降级为 `UNKNOWN`，更新 attribution 后再重审。

## 学术与方法论来源

下列来源只贡献可引用的思想背景；本项目没有复制论文 PDF、图表、数据集、代码或长段文本：

| Work | 使用决定 | 再分发结论 |
|---|---|---|
| Cohen & Frazzini, “Economic Links and Predictable Returns” | supply-chain information diffusion / customer momentum 背景。 | 仅书目信息和方法概念；不再分发论文内容。 |
| Pinchuk, “Customer Momentum”，<https://arxiv.org/abs/2301.11394> | customer momentum 背景。 | 仅引用；不打包论文或数据。 |
| Teece, “Profiting from technological innovation” | appropriability 与 complementary assets 背景。 | 仅书目信息和方法概念。 |
| Adner & Kapoor, “Value Creation in Innovation Ecosystems” | ecosystem interdependence / adoption bottleneck 背景。 | 仅书目信息和方法概念。 |
| Cooper, Gulen & Schill, “Asset Growth and the Cross-Section of Stock Returns” | capital-cycle / asset-growth discipline 背景。 | 仅书目信息和方法概念。 |

完整 bibliography URL 位于 canonical `references/source_catalog.md`。每个 live investment claim 仍必须独立
刷新一手来源；bibliography 本身不能确认任何当前市场事实。

## OpenAI Skill 文档

OpenAI 的 `Build skills`、`Testing Agent Skills Systematically with Evals` 与 API `Skills` 文档仅用于 Skill
目录、metadata、progressive disclosure 与 eval 工程约定。未复制其文档正文或示例 payload；UI metadata 由
本机官方 skill-creator generator 确定性生成。链接见 canonical `references/source_catalog.md`。

## 输入 notice 的迁移结果

- 仅用于研究与教育；不含 broker integration 或 trade execution。
- 市场数据、filing 与 thesis 会衰减；每次必须记录 `as_of` 与 source cutoff。
- 社交媒体业绩不视为已审计，除非有完整 broker statements、完整仓位历史、sizing 与亏损披露。
- bundled examples 使用合成实体和数字，不能作为 live investment evidence。

## MIT notice — muxuuu/serenity-skill

```text
MIT License

Copyright (c) 2026 muxu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 再分发结论

1. canonical Skill、Task Pack 与外层项目可在 MetaDatabase 根 proprietary 条款下保存和发布；识别出的
   muxuuu scaffolding 同时保留其 MIT notice，MIT 权利不被本项目 proprietary 条款收回。
2. 当前 payload 不包含 yan-labs 或 wesson9527 的 code/data/media/docs，也不包含 X posts、论文 PDF、付费数据、
   live market data、真实账户/组合或客户材料。
3. 输入 ZIP 只作为本地迁移证据，不提交、不安装、不充当 current release；current release 必须从 canonical
   source 确定性构建。
4. 任何新增第三方 payload 必须先记录来源、固定版本、许可、复制范围和再分发条件；未知许可默认排除并阻断 release。
