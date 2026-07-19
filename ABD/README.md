# ABD Product Design TaskPack `0.0.0.1`

这是ABD最终开发任务包。它不是已完成的软件，而是无歧义、机器可执行、可验收、可回滚的开发/部署/运行合同。

## 当前开发状态

- `S00/P01`、`S00/P02` 与 `S00/P03` 已分别由独立证据标为 `PASS`；
- 任务包自身的 `PASS` 只表示“开发合同可交接”，不表示 ABD 已上线、已部署或已验证收益；
- `S00/P04` 尚未开始；Stage 0 当前完成 3/4 个 Phase，尚未通过整体复审，也未上传 GitHub；
- P02 冻结的是授权规则，不证明 OVH、Cloudflare、GitHub、Gmail 或任何平台凭证/能力当前可用；
- P03 只证明当前声明依赖的 ABD 新增现金成本为 A$0、付费接口不在关键路径；既有 OVH/账户总成本、外部能力与免费额度余量仍未知；
- 当前禁止真实下单，30% 月度滚动复利只是待证伪和长期验证的目标，不是收益保证。

`S00/P03` 的定向与全回归验证命令：

```bash
uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py
uv run --frozen --python 3.12 python machine/tools/validate_pack.py
uv run --frozen --python 3.12 python -m pytest -q tests/S00/P03_test.py --junitxml=machine/evidence/S00/P03/pytest.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S00/P03/pytest.xml
uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S00/P03/full_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S00/P03/full_regression.xml
uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S00-P03 --evidence machine/evidence
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
