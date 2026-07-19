# Restore and verify

## 从 GitHub main 恢复

```bash
git clone --filter=blob:none --sparse git@github.com:LinzeColin/MetaDatabase.git
cd MetaDatabase
git sparse-checkout set stock-commercial-opportunities-skill
cd stock-commercial-opportunities-skill
env LC_ALL=C LANG=C LC_CTYPE=C shasum -a 256 -c BACKUP_MANIFEST.sha256
```

## 验证历史谱系

```bash
env LC_ALL=C LANG=C LC_CTYPE=C shasum -a 256 \
  archives/research-high-roi-content_codex-skill-task-pack_v1.0.0.zip \
  archives/commercial-opportunity-decomposition_codex-skill-task-pack_v2.0.0.zip
```

预期分别为：

```text
73f6934529b401a33271e8bc2f2bf7c89979a2dbb56e92e5abb4e8ff2fc40792
01c3d8b069d488cddb4fa3c85959a89bd9b5d072c4b1437cced03073e0442fc4
```

## 验证 v3

```bash
cd task-pack
SKILL=skill_draft/stock-commercial-opportunities
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$SKILL/tests" -p 'test_*.py' -v
python3 "$SKILL/scripts/validate_skill.py" "$SKILL" --strict
python3 "$SKILL/scripts/validate_deliverable.py" --input "$SKILL/assets/deliverable.example.json" --strict
env LC_ALL=C LANG=C LC_CTYPE=C shasum -a 256 -c MANIFEST.sha256
cd ../releases
env LC_ALL=C LANG=C LC_CTYPE=C shasum -a 256 -c SHA256SUMS
unzip -t stock-commercial-opportunities_codex-skill-task-pack_v3.0.0.zip
```

恢复完成只证明源码/任务包完整，不代表本地安装、隐式触发、投资结论或交易系统可用。
