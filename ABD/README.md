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
- `S01/P01` 至 `S01/P04` 只冻结客户体验、疑问、需求、范围、指标、经济和证伪合同，不证明产品已实现、部署、接入账户或验证收益；四个中间 Phase 均未单独上传 GitHub；
- `S00/P02` 冻结的是授权规则，不证明 OVH、Cloudflare、GitHub、Gmail 或任何平台凭证/能力当前可用；
- `S00/P03` 只证明当前声明依赖的 ABD 新增现金成本为 A$0、付费接口不在关键路径；既有 OVH/账户总成本、外部能力与免费额度余量仍未知；
- `S00/P04` 冻结 Gmail 可选 consent、精确 scope、方法白名单和降级状态机；本 phase 未生成 OAuth 链接、未访问账户、未取得或保存 token、未调用 Gmail API，Gmail 仍为 `NOT_CONNECTED / UNVERIFIED / NOT_READY`；
- 当前禁止真实下单，30% 月度滚动复利只是待证伪和长期验证的目标，不是收益保证。

当前 `S02/P01` 的定向与全回归验证命令：

```bash
uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py
uv run --frozen --python 3.12 python machine/tools/validate_pack.py
uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing STAGE-REVIEW-S01
uv run --frozen --python 3.12 python -m pytest -q tests/S02/P01_test.py --junitxml=machine/evidence/S02/P01/pytest.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/P01/pytest.xml
uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S02/P01/full_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/P01/full_regression.xml
uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S02-P01 --evidence machine/evidence
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
