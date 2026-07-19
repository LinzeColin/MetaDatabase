# stock-commercial-opportunities-skill

“股票商业机会拆解”Codex Skill 的专有源码项目与可恢复备份。稳定调用 ID：`stock-commercial-opportunities`。

本项目把产业/商业机会映射为上市公司研究候选，要求证明“商业价值池 → 受益路径 → 发行人敞口 → 订单/收入/利润或现金流捕获 → 当前预期/估值/催化”的证据链。输出是研究优先级，不是个性化投资建议、买卖指令或收益保证。

## 当前版本

- Version：`3.0.0`
- Status：`SOURCE_PACKAGE_READY / NOT_INSTALLED / SEMANTIC_FORWARD_EVAL_NOT_RUN`
- Repository：MetaDatabase（PUBLIC repository，专有许可）
- Local install：禁止；本项目只保存源码与验证材料

## 目录

```text
stock-commercial-opportunities-skill/
├── README.md
├── AGENTS.md
├── VERSION
├── CHANGELOG.md
├── SOURCE_INVENTORY.md
├── RESTORE_AND_VERIFY.md
├── BACKUP_MANIFEST.sha256
├── task-pack/                 # v3 可读源码与完整任务包
│   └── skill_draft/stock-commercial-opportunities/
├── releases/                  # v3 可移植 ZIP 与 SHA
└── archives/                  # 原始 v1 与通用商业机会 v2 谱系
```

## 快速验证

```bash
cd task-pack
SKILL=skill_draft/stock-commercial-opportunities
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$SKILL/tests" -p 'test_*.py' -v
python3 "$SKILL/scripts/validate_skill.py" "$SKILL" --strict
python3 "$SKILL/scripts/validate_deliverable.py" --input "$SKILL/assets/deliverable.example.json" --strict
python3 "$SKILL/scripts/score_stock_opportunities.py" --input "$SKILL/assets/stock-opportunity-score-input.example.json" --format markdown
```

完整恢复与哈希验证见 `RESTORE_AND_VERIFY.md`。仓库为公开可见，不得提交客户材料、投资组合、账户、交易、付费数据、MNPI、凭据或本机证据。
