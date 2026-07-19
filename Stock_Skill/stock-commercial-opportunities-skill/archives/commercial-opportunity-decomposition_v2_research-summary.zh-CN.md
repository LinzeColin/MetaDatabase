# 商业机会拆解 Skill v2：研究与改进摘要

## Outcome

原 v1 更接近“高 ROI 内容研究/选题”，无法可靠回答商业机会是否值得做。v2 已重构为：

- 中文名：**商业机会拆解**
- 推荐调用 ID：`qualify-commercial-opportunities`
- 版本：`2.0.0`（breaking redesign）
- 核心输出：证据校准的机会资格、成熟度、Go/No-Go 门禁与最高 VOI 下一实验
- 内容/脚本：仅作为资格审查后的可选 activation layer

## 公开研究得到的关键设计结论

1. [Product Talk Opportunity Solution Tree](https://www.producttalk.org/2016/08/opportunity-solution-tree/)说明机会树依赖目标客户、outcome 和故事型客户访谈；桌面研究不能凭空证明机会。
2. [Strategyzer Test Card](https://www.strategyzer.com/library/validate-your-ideas-with-the-test-card)支持在实验前明确假设、方法、指标和阈值。
3. [Expected Parrot EDSL](https://github.com/expectedparrot/edsl)明确提示 AI 模拟响应不代表真实人口意见，应由真实人类数据验证。
4. [Emotix OSS](https://github.com/agshinrajabov/emotix-oss)的失败复盘显示：产品管线能工作仍可能没有 PMF，distribution 必须是一等公民。
5. [GPT Researcher Issues](https://github.com/assafelovic/gpt-researcher/issues)暴露了伪来源、来源质量评分与 search snippet 被当成全文等研究完整性风险。

## v2 关键机制

- 两轴分离：机会吸引力 vs. 证据成熟度 `M0`–`M5`。
- 公开桌面研究最高 `M1 Desk-qualified`。
- 决策状态：`STOP / WATCH / TEST_NEXT / GO_PILOT / GO_SCALE`。
- 高分不能绕过成熟度；合成 persona 不能支持真实需求成熟度。
- user、problem owner、payer、budget owner、veto 分开。
- distribution/procurement 与 buyer budget 同为一级评分维度。
- 固定 12/Top 3 改为 cap + saturation；允许 `NO_QUALIFIED_OPPORTUNITY`。
- Source Register、access level、URL allowlist、private/public redaction。
- Validation Card 强制行为/分母/pass/fail/timebox/cap/三分支。
- 默认只给一个最高价值信息（VOI）的下一实验。

## 交付物

任务包包含：

- 研究报告与参考项目矩阵；
- 任务颗粒度 R00–H01 与 RC-0–RC-3 Run Contracts；
- 可 staging 的 Skill 草案、9 个 reference、3 个标准库脚本；
- intake、Opportunity Card、Validation Card、证据台账与结构化示例；
- 22 个触发用例、8 个质量用例、benchmark schema；
- 26 个确定性回归测试、验收清单、盲点/Surprise、迁移与 License 边界。

## 当前验证状态

| Gate | 状态 |
|---|---|
| 本地 package/deliverable strict validators | PASS：0 error / 0 warning |
| Python tests | PASS：26/26 |
| scorer fixture | PASS：M3/GO_PILOT、M2/TEST_NEXT、M1/STOP 分离正确 |
| JSON/JSONL/CSV/YAML/links/stdlib/cache | PASS |
| 当前官方 quick validator | NOT_AVAILABLE（活动工具路径未暴露；未用旧备份冒充） |
| 新鲜线程隐式触发 | NOT_RUN |
| 无 Skill / 有 Skill质量 A/B | NOT_RUN |
| 全局安装与发现 smoke | NOT_RUN；本次未授权安装 |
| 真实客户需求/付费/交付 | NOT_RUN；不能声称机会已验证 |

最终 ZIP SHA-256：`01c3d8b069d488cddb4fa3c85959a89bd9b5d072c4b1437cced03073e0442fc4`；压缩包完整性测试通过。

## 盲点与 Surprise Top 3

1. 最有价值的输出可能是更早 `STOP`，不是强行找到赢家。
2. 分发不是产品完成后的 GTM 尾声，而是机会定义的一部分。
3. 一笔付款仍不等于可规模化；交付、复购和单位经济分别对应更高门禁。

## 唯一待确认项

是否接受新调用 ID `qualify-commercial-opportunities`。推荐接受：它准确表达 v2 核心工作，且只读检查未发现两个常见用户级根中存在已安装旧版。确认后再单独执行新鲜线程语义评估与可回滚安装。
