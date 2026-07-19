# v3 任务包验证报告

> 验证日期：2026-07-19
> 环境：macOS 15.1；Python 3.9.6；Git 2.39.5
> 对象：`skill_draft/stock-commercial-opportunities/`

## 结论

v3 源码包确定性 Gate **PASS**：Skill 结构、股票专用 references/templates、synthetic fixtures、三个标准库脚本、29 个回归测试、数据格式、YAML、相对链接、依赖、cache/secret/local-path 和研究状态门禁均通过。

发布 Gate 以 `MANIFEST.sha256`、项目 `releases/SHA256SUMS`、clean-room 解压复测和根 `BACKUP_MANIFEST.sha256` 为准。当前官方 Skill `quick_validate.py` 未在活动 Skill 根发现，状态 **NOT_AVAILABLE**，不是 PASS。

隐式触发、无/有 Skill 模型 A/B、用户级安装/发现和任何真实证券研究均为 **NOT_RUN**。所有 ticker/issuer/exchange 样例是 `DEMO` synthetic fixtures。因此只能声称“v3 source package deterministic/recovery checks 通过”，不能声称“Skill 已安装”“模型语义效果已验证”或“存在真实投资机会”。

## 状态矩阵

| 项目 | 状态 | 同次证据 |
|---|---|---|
| 股票专用公开研究 | PASS | `RESEARCH_REPORT.md`, `REFERENCE_PROJECT_MATRIX.md` |
| Skill package validator strict | PASS | `PASS: 0 error(s), 0 warning(s)` |
| Deliverable validator strict | PASS | `PASS: 0 error(s), 0 warning(s)` |
| Stock scorer fixtures | PASS | S001=75.4/E5/ADVANCE_RESEARCH；S002=65.1/E3/DILIGENCE_NEXT；S003=0.0/E0/REJECT |
| Unit + CLI regressions | PASS | `Ran 29 tests ... OK` |
| Python compile | PASS | 4 files；cache 定向到 task-pack 外部临时路径 |
| JSON | PASS | assets 2/2 可解析 |
| JSONL | PASS | trigger=22（12 positive/10 negative）；quality=8 |
| CSV | PASS | benchmark header=43 columns |
| YAML | PASS | Ruby stdlib parse；interface/policy 为 mappings |
| Markdown local links | PASS | 17 个相对链接存在且不逃逸 task-pack |
| Python imports | PASS | AST allowlist 全为标准库 |
| Cache/temp | PASS | 包内无 pycache/pyc/pyo/log/tmp/DS_Store |
| Secret/local path scan | PASS | private-key/API-token/真实用户路径/session/account pattern 无命中 |
| 当前官方 quick validator | NOT_AVAILABLE | 活动 Skill 根未发现 `skill-creator/quick_validate.py` |
| Task-pack manifest | PASS | `shasum -a 256 -c MANIFEST.sha256` |
| Release ZIP integrity/path safety | PASS | `unzip -t`；无绝对/`..`/symlink entry |
| Clean-room release tests | PASS | 解压副本重复 manifest、29 tests、两个 strict validators |
| Root backup manifest | PASS | 项目根 `shasum -a 256 -c BACKUP_MANIFEST.sha256` |
| Fresh-task implicit trigger | NOT_RUN | 22 cases 已备，无真实模型输出 |
| No-Skill / with-Skill A/B | NOT_RUN | 8 cases/rubric 已备，无 paired output |
| Local install/discovery | NOT_RUN | 用户明确禁止本地安装 |
| Live issuer/current market research | NOT_RUN | fixtures 全 synthetic；无 price/consensus/portfolio/account |

## 实际阻断命令

```bash
SKILL=skill_draft/stock-commercial-opportunities
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$SKILL/tests" -v
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL/scripts/validate_skill.py" "$SKILL" --strict
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL/scripts/validate_deliverable.py" \
  --input "$SKILL/assets/deliverable.example.json" --strict
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL/scripts/score_stock_opportunities.py" \
  --input "$SKILL/assets/stock-opportunity-score-input.example.json" --format markdown
```

结果：29/29 PASS；两个 strict validator 均 0 error / 0 warning；scorer 输出三种预期 Gate。

```bash
env LC_ALL=C LANG=C LC_CTYPE=C shasum -a 256 -c MANIFEST.sha256
unzip -t ../releases/stock-commercial-opportunities_codex-skill-task-pack_v3.0.0.zip
```

随后在临时解压目录重复 manifest、tests 和 strict validators。release 的 canonical SHA-256 位于项目 `releases/SHA256SUMS`，避免在 ZIP 内形成自引用 hash。

## 覆盖的失败模式

- 高分 E1 不得超过 SCREEN_FLAG；hard stop 强制 REJECT。
- E4/score/confidence 不足不能 ADVANCE_RESEARCH；synthetic fixture 不能升级。
- unsupported claim、unregistered URL、snippet/synthetic-only core fact、maturity mismatch 被阻断。
- public output 中未脱敏 private source、无证据却 completed diligence 被阻断。
- 收益保证、个人交易动作、真实用户路径、缺 primary high-stakes source 被阻断。
- 零候选与 `NO_QUALIFIED_CANDIDATE` 是合法结果。

## 诚实限制

1. Scorer 权重和 E-level 数量门槛是透明启发式，未用真实投资 outcome 校准。
2. 静态 validators 只能检查合同，不能证明 filing 内容、当前 price/consensus 或投资论点正确。
3. 产品官方页面是供应商自述；未购买/登录商业数据服务。
4. 官方 Skill 工具链会变化；未来使用前应按当前文档再验。
5. 语义触发/A-B 未运行，本地安装明确不在本次范围。

## 下一 Gate

若未来需要证明实际可用性，最高 ROI 下一步是在**不安装**条件下，用新鲜任务显式加载源码，对 Q01/Q04/Q05/Q08 做 paired A/B 并保存公开安全原始输出；当前交付不应扩大到真实股票或交易动作。
