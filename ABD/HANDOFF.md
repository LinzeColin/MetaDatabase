# ABD 开发交接

## 当前目标

在 `codex/abd-v0001-s09-p01` 完成 S09 的本地 Phase 与整体复审；下一轮只能执行一次 S09 GitHub 阶段上传。上传前不得开始 S10；上传并得到相应远端证据前不得部署或激活生产。

## 当前状态

- S09/P01--P04 保持已签名通过：`machine/evidence/EVD-S09-P01.json` 至 `EVD-S09-P04.json`。无可复现领域增量时残差权重严格为 `0`；市场权重不低于各冻结合同下限。
- S09/P02 的特征只选择 `known_at <= decision_at` 的最新值；缺失、未来或未确认参赛状态回退为市场基线。S09/P03 的 Poisson、Dixon--Coles、Skellam 与负二项分布使用 50 位十进制概率质量及显式尾部。
- 足球模型只在全部特征于建议时已知、参赛状态确认且所有有限支持尾部不高于 `1e-12` 时融合残差；未来、缺失、未确认或高尾部均回退为原始市场向量，残差权重为 `0`。
- S09/P04「赛马、篮球、棒球及小众回退」已签名通过：`machine/evidence/EVD-S09-P04.json`（SHA-256 `e38e3c5bbbdfb1cfe6a345bcf0511e0ccf7c65e5b78415d62cfd44fd1c5332ef`）。赛马使用冻结的 Plackett--Luce 胜者与 Harville exacta 概率；篮球使用节奏--效率投影；棒球使用先发/牛棚与球场因子投影。三者只在决策时已知且参赛确认的可复现输入中融合受限残差，市场权重保持至少 `0.65`。
- 赛马未来特征、篮球未确认状态及所有小众领域均已确定性回退到 `MARKET_ONLY_OR_NO_ADVICE`：残差权重 `0`、市场权重 `1`，不会生成建议或订单。
- S09 整体复审已本地签名通过：`machine/evidence/EVD-S09-STAGE-REVIEW.json`（SHA-256 `7af6ce0744091df3208b8d67b7aa6ce679918f766e0fea701ab168c852238860`），下一状态为 `S09/GITHUB_STAGE_UPLOAD_READY`。
- 复审发现并解决真实流程缺口 `S09-REVIEW-001`：四个 Phase 有签名证据但任务包未预置整体复审合同。解决方式是新增离线复审合同，绑定 P01--P04 的证据及回滚哈希；未修改冻结 Phase 基线。
- 全部复审只使用冻结合成输入。未访问网络、真实市场、账户、Gmail、OVH 或 Cloudflare；未生成建议或订单，未上传 GitHub、未部署或激活生产，现金新增支出为 `A$0.00`。

## 已验证

- S09/P01--P04 现有证据复验均 PASS；每份 Phase 的冻结证据与回滚哈希均被整体复审重新绑定。
- `tests/S09/stage_review_test.py`：41 passed（仅此复审的定向测试）。
- `STAGE-REVIEW-S09`：77/77 checks PASS；`python -m abd_acceptance.stage9_review --verify-existing --evidence machine/evidence` PASS。
- 付费/未知依赖扫描 PASS；Task Pack 49/49 PASS；制品清单更新 PASS（manifest 576 files，checksum 577 files）。
- 100 次冻结重放与 10,000 次 CPU-only 冻结不利扰动均通过；`real_time_wait_performed=false`，未进行全量测试、完整回归或真实时间 soak。

## 关键文件

- `score_models.py`
- `football_model.py`
- `distribution_tests.json`
- `abd_acceptance/score_football_models.py`
- `machine/tests/fixtures/S09_P03.json`
- `machine/evidence/EVD-S09-P03.json`
- `racing_model.py`
- `basketball_model.py`
- `baseball_model.py`
- `niche_fallback.json`
- `abd_acceptance/multi_sport_fallback.py`
- `machine/tests/fixtures/S09_P04.json`
- `machine/evidence/EVD-S09-P04.json`
- `machine/facts/stage9_review_contract.json`
- `machine/tests/fixtures/S09_STAGE_REVIEW.json`
- `abd_acceptance/stage9_review.py`
- `tests/S09/stage_review_test.py`
- `machine/evidence/S09/STAGE_REVIEW/findings.json`
- `machine/evidence/EVD-S09-STAGE-REVIEW.json`
- `machine/evidence/EVD-S09-STAGE-REVIEW_rollback.json`

## 下一步

下一轮只执行一次 S09 GitHub 阶段上传：先复验本地 S09 整体复审证据、提交范围、远端与分支合同，再上传并读取远端结果。不得开始 S10；不得运行全量测试、完整回归或真实时间 soak。GitHub 上传本身不构成 OVH、Cloudflare、市场、账户、收益或生产部署已验证的声明。
