# ABD Product Design TaskPack `0.0.0.1`

这是ABD最终开发任务包。它不是已完成的软件，而是无歧义、机器可执行、可验收、可回滚的开发/部署/运行合同。

## 当前开发状态

- `S00/P01`、`S00/P02`、`S00/P03` 与 `S00/P04` 已分别由独立证据标为 `PASS`；
- 任务包自身的 `PASS` 只表示“开发合同可交接”，不表示 ABD 已上线、已部署或已验证收益；
- Stage 0 已完成 4/4 个 Phase；本地整体复审的 45/45 门、定向测试 54/54、全回归 206/206 与任务包校验 49/49 均为 `PASS`；
- Stage 0 已通过 GitHub PR #58 合并到 `main`；两条 main CI 成功记录已固化为不可变交付收据，并由离线 Git 历史再次验证；
- `S01/P01` 已完成客户新闻稿与客户结果合同，独立 Oracle 67/67、定向测试 80/80、全回归 286/286 与任务包校验 49/49 均为 `PASS`；证据下一状态严格为 `S01/P02_READY_NOT_STARTED`；
- `S01/P02` 已完成客户 FAQ 与假设登记册，独立 Oracle 93/93、定向测试 239/239、全回归 525/525 与任务包校验 49/49 均为 `PASS`；证据下一状态严格为 `S01/P03_READY_NOT_STARTED`；
- `S01/P03` 已冻结 21 条唯一产品需求、5 条业务线、18 个功能模块、8 条主流程和 13 条显式安全错误路径；含外部报告门的独立 Oracle 110/110、定向测试 132/132、全回归 658/658 与任务包校验 49/49 均为 `PASS`；
- `S01/P04` 已冻结 31 个指标、五项非现金收益测量、成本/ROI 未知默认和 19 条前瞻 kill criteria；整体复审发现的四条未测需求已修复，独立 Oracle 133/133、定向测试 157/157、全回归 815/815 与任务包校验 49/49 均为 `PASS`；
- `S01 整体复审` 的 61/61 门、定向测试 87/87、全回归 902/902、TaskPack 49/49、付费依赖扫描与 7/7 回滚均为 `PASS`；Stage 1 已通过 GitHub PR #64 合并到 `main`，两条 main CI 成功记录、A$0 交付门和离线 Git 历史已固化为不可变交付收据；
- `S02/P01` 已冻结 24 个官方一手来源、23 条平台事实与 9 条监管控制，共 32 个唯一 claim；含外部报告门的独立 Oracle 88/88、定向测试 158/158、全回归 1060/1060、TaskPack 49/49、付费依赖扫描与 7/7 回滚均为 `PASS`，证据下一状态严格为 `S02/P02_READY_NOT_STARTED`；本 Phase 仅本地开发，尚未单独上传 GitHub；
- `S02/P01` 明确拒绝把 TAB Studio/Web Services、Sportsbet 自动化、Gmail、Cloudflare 或 OVH 写成已授权或已连接能力；Cloudflare 中国网络不属于 A$0 范围，普通全球网络上的中文界面不等于中国大陆境内加速、可用性或可达性保证；
- `S02/P02` 已冻结 8 篇一手论文、14 条可追溯模型与风险主张，以及 18 个明确不得冒充论文推导值的本地阈值；含外部报告门的独立 Oracle 90/90、定向测试 161/161、全回归 1221/1221、TaskPack 49/49、付费依赖扫描与 8/8 回滚均为 `PASS`，证据下一状态严格为 `S02/P03_READY_NOT_STARTED`；本 Phase 仅本地开发，尚未单独上传 GitHub；
- `S02/P02` 只固化市场先验、校准与 proper scoring、不建议区域、异常敏感性和受限凯利的研究边界；未训练或执行模型、未回测、未验证全部市场、未接入账户、未部署，也不证明任何收益或风险保证；
- `S02/P03` 已在固定 Git commit 上审计 flumine、penaltyblog、OddsHarvester 等 6 个公开仓库，逐项冻结 adopt/adapt/reject、许可证和来源合同决定；4 个 MIT、1 个 Apache-2.0、1 个未检测到许可证，未检测到许可证的仓库禁止代码复用；含外部报告门的独立 Oracle 93/93、定向测试 218/218、全回归 1439/1439、TaskPack 49/49、付费依赖扫描与 8/8 回滚均为 `PASS`，证据下一状态严格为 `S02/P04_READY_NOT_STARTED`；本 Phase 仅本地开发，尚未单独上传 GitHub；
- `S02/P03` 没有复制候选代码、clone 仓库、安装依赖、调用外部 API/账户、绕过站点控制或花费新增现金；仓库许可证不替代网站、数据、API、账户、再分发或商业服务条款，GitHub 自动许可证检测也不构成法律许可；
- `S02/P04` 已把 P01–P03 的显式未知、未验证前置、模型主张、本地阈值、复用限制和监管适用性归并为 26 个明确开放缺口；Stage 2 整体复审发现其中 3 个 gap 缺少直接 counterevidence，已新增 CE-S02-P04-020 至 022 并把 26/26 双向覆盖升级为 fail-closed Oracle 门；26 个缺口仍全部保持 `OPEN_EXPLICIT`，已解决 0、静默缺口 0，登记、反证或安排复审均不等于解决；四个中间 Phase 均仅本地开发，尚未单独上传 GitHub；
- `S02 整体复审` 已冻结并解决 4 条 findings，覆盖跨 Phase 来源图、历史 commit/收据重放、A$300/A$0、无自动下单、无收益保证、全回归与回滚门；GitHub 上传预检暴露的绝对本地路径变异测试跨平台缺口已通过 POSIX/Windows/UNC/file URI 统一拒绝规则修复；独立 Oracle 63/63、定向测试 339/339、全回归 2155/2155、TaskPack 49/49、付费依赖扫描与 13/13 回滚均为 `PASS`，下一状态严格为 `S02/GITHUB_STAGE_UPLOAD_READY`；阶段分支已上传但尚未上传至 GitHub `main`，远端成功 CI 尚未观察，`S03` 尚未开始；
- `S02/P04` 与整体复审没有新增网络调研、访问平台或云账户、调用 API、clone/安装候选、执行模型、部署生产、提供真实下单能力或花费新增现金；30% 月度滚动复利目标仍为待证伪、未验证且不保证的目标；
- `S01/P01` 至 `S01/P04` 只冻结客户体验、疑问、需求、范围、指标、经济和证伪合同，不证明产品已实现、部署、接入账户或验证收益；四个中间 Phase 均未单独上传 GitHub；
- `S00/P02` 冻结的是授权规则，不证明 OVH、Cloudflare、GitHub、Gmail 或任何平台凭证/能力当前可用；
- `S00/P03` 只证明当前声明依赖的 ABD 新增现金成本为 A$0、付费接口不在关键路径；既有 OVH/账户总成本、外部能力与免费额度余量仍未知；
- `S00/P04` 冻结 Gmail 可选 consent、精确 scope、方法白名单和降级状态机；本 phase 未生成 OAuth 链接、未访问账户、未取得或保存 token、未调用 Gmail API，Gmail 仍为 `NOT_CONNECTED / UNVERIFIED / NOT_READY`；
- 当前禁止真实下单，30% 月度滚动复利只是待证伪和长期验证的目标，不是收益保证。

当前 `S02 整体复审` 的定向与全回归验证命令：

`S02/P01` 至 `S02/P04` 的历史前置由 `tests/S02/P01_test.py`、`tests/S02/P02_test.py`、`tests/S02/P03_test.py`、`tests/S02/P04_test.py`、不可变证据、历史 Git commit 与 `python -m abd_acceptance --verify-existing STAGE-REVIEW-S01` 重放验证；以下命令只列整体复审的新增验证。

```bash
uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py
uv run --frozen --python 3.12 python machine/tools/validate_pack.py
uv run --frozen --python 3.12 python -m pytest -q tests/S02/stage_review_test.py --junitxml=machine/evidence/S02/STAGE_REVIEW/pytest.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/STAGE_REVIEW/pytest.xml
uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S02/STAGE_REVIEW/full_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/STAGE_REVIEW/full_regression.xml
uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S02 --evidence machine/evidence
uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py
```

## 交付

- `文档/`：严格7份人类平面文档；
- `machine/facts/`：Canonical Facts、参数、需求、验收、任务图、追踪、研究、安全和发布真源；
- `machine/schemas/`：机器合同Schema；
- `machine/tools/`：文档重生和任务包校验；
- `machine/tests/fixtures/`：数值、调度和邮件安全边界夹具；
- `machine/evidence/`：校验、追踪、路线图、清单和证据索引；
- `skill/`：完善后的Product-Design-Taskpack Skill；
- `PURSUE_GOAL_PROMPT.txt`：开发线程持续目标；
- `VERSION`：精确版本。

## 运行校验

```bash
python machine/tools/render_human.py
python machine/tools/validate_pack.py
```

通过后检查：

```text
machine/evidence/validation_report.json
machine/evidence/SHA256SUMS
```

## 关键边界

- 系统只分析和建议，不提交真实订单；
- 用户正常只完成最终下单；
- OVH全天候主运行，Cloudflare全球中文访问；
- 新增现金预算A$0；
- 所有距开始>24小时事件每30分钟刷新；
- Gmail邮件每15分钟确定性归档，验证后移入垃圾箱，Codex每天审计；
- 权威数值使用十进制定点，±0.0001和不利赔率跳动翻转即不建议；
- 30%月复利是目标、容量、证伪和长期验证合同，不是随机收益保证。
