#!/usr/bin/env python3
from __future__ import annotations
import sys
# 这些脚本会 import signal_lattice，默认会在源码树里留下 __pycache__，
# 而 verify_package 又把 __pycache__ 判为构建垃圾——建清单这一步会自己制造自己的红灯。
sys.dont_write_bytecode = True
import argparse,json,re,tomllib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from signal_lattice.constants import VERSION
VERSION_RE=re.compile(r'0\.0\.0\.\d+\.\d+')
# 必须存在版本号的文件；缺失即报 MISSING_VERSION_FILE。
REQUIRED_VERSION_FILES=(
 'CANONICAL_STATE.json','00_READ_FIRST.md','README.md','ACTIVE_RELEASE.md','ROADMAP.md','CODEX_LAST_MILE_PROMPT.txt',
 'machine/facts/project.json','machine/facts/requirements.json','machine/facts/task_dag.json',
 'machine/facts/acceptance_contract.json','machine/facts/release_boundary.json',
 'openapi.yaml','events.yaml','文档/00_我在哪.md'
)
# 版本漂移改为全树扫描：白名单漏掉一个文件就是一次静默漂移，2026-09-14 一次版本升级里
# machine/facts 下有 11 个文件因此被漏掉。存档与派生产物除外。
SCAN_EXCLUDE_PREFIXES=('v19_release/','Stock_Skill/','evidence/','.git/')
SCAN_EXCLUDE_NAMES={'MANIFEST.json','SUBJECT_LOCK.json','V19_CANONICAL_STATE.json'}
SCAN_SUFFIXES={'.py','.json','.md','.yaml','.yml','.txt','.html','.sh','.toml','.service','.timer','.env','.example'}
# 历史引用豁免：文件正当地提到某个旧版本（回滚目标、v19 封包版本、合成的上一版发布）。
# 默认全树扫描，任何未在此登记的旧版本串一律判为漂移——例外必须写明理由，不允许静默通过。
HISTORICAL_VERSION_EXEMPTIONS={
 'MEMORY_RECONCILIATION.md':({'0.0.0.1.38','0.0.0.1.40'},'历史记录：过去两条交付路线的版本'),
 'docs/DEPLOYMENT_RESULT_CONTRACT.md':({'0.0.0.1.41'},'v19 封包契约存档'),
 'docs/PRODUCT_RESULT.md':({'0.0.0.1.41'},'v19 成果存档'),
 'schemas/delivery_result.schema.json':({'0.0.0.1.41'},'v19 封包 schema，约束的是 v19 回执'),
 'schemas/status_snapshot.schema.json':({'0.0.0.1.41'},'同上'),
 'schemas/taskpack_owner_approval.schema.json':({'0.0.0.1.41'},'同上'),
 'schemas/taskpack_seal.schema.json':({'0.0.0.1.41'},'同上'),
 'scripts/deploy_northstar.sh':({'0.0.0.1.41'},'v19 部署路径；v2 用 scripts/install_release.sh，不走这里'),
 'scripts/verify_northstar_repair_authorization.py':({'0.0.0.1.41'},'v19 授权校验存档'),
 'tests/test_formal_lifecycle.py':({'0.0.0.1.41'},'v19 封包生命周期回归'),
 'tests/test_preparation_tools.py':({'0.0.0.1.45'},'v19 wheel 文件名'),
 'tests/test_public_release.py':({'0.0.0.1.41'},'v19 发布回归'),
 'tests/test_repair_security.py':({'0.0.0.1.41'},'v19 修复授权回归'),
 'tests/test_taskpack_seal.py':({'0.0.0.1.41'},'v19 封包回归'),
 'tests/test_deployment_northstar.py':({'0.0.0.2.2'},'合成的上一版发布，用于验证回滚路径'),
 'CANONICAL_STATE.json':({'0.0.0.2.3','0.0.0.2.4','0.0.0.2.5','0.0.0.2.6','0.0.0.2.7'},'previous_version：生产上一版发布目录，回滚目标'),
 'HANDOFF.md':({'0.0.0.2.3','0.0.0.2.4','0.0.0.2.5','0.0.0.2.6','0.0.0.2.7'},'同上，交接文档记录 previous 指向'),
 'deploy/ROLLBACK_V2.md':({'0.0.0.1.43','0.0.0.2.3','0.0.0.2.4','0.0.0.2.5','0.0.0.2.6','0.0.0.2.7'},'回滚目标：v19 发布目录名，以及 v2 历次上一版'),
}


def scan_targets(root):
 for path in sorted(root.rglob('*')):
  if not path.is_file():continue
  rel=path.relative_to(root).as_posix()
  if rel.startswith(SCAN_EXCLUDE_PREFIXES):continue
  if path.name in SCAN_EXCLUDE_NAMES:continue
  if path.suffix not in SCAN_SUFFIXES:continue
  yield rel,path
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--output',type=Path);a=p.parse_args();root=a.root.resolve();find=[]
 py=tomllib.loads((root/'pyproject.toml').read_text());declared=py['project']['version']
 if declared!=VERSION:find.append(f'PYPROJECT_VERSION_DRIFT:{declared}:{VERSION}')
 for rel in REQUIRED_VERSION_FILES:
  if not (root/rel).is_file():find.append('MISSING_VERSION_FILE:'+rel)
 for rel,path in scan_targets(root):
  try:text=path.read_text(encoding='utf-8')
  except (UnicodeDecodeError,OSError):continue
  # 本文件自身就是豁免登记表，表里必然写着那些旧版本串，跳过对它的扫描。
  if rel=='scripts/verify_version_lock.py':continue
  values=set(VERSION_RE.findall(text))
  allowed,_reason=HISTORICAL_VERSION_EXEMPTIONS.get(rel,(set(),''))
  drift=sorted(values-{VERSION}-allowed)
  if drift:find.append(f'VERSION_DRIFT:{rel}:{drift}')
 state=json.loads((root/'CANONICAL_STATE.json').read_text())
 for key in ('product_version','taskpack_version'):
  if state.get(key)!=VERSION:find.append(f'CANONICAL_VERSION_DRIFT:{key}')
 project=json.loads((root/'machine/facts/project.json').read_text())
 for key in ('product_version','taskpack_version'):
  if project.get(key)!=VERSION:find.append(f'PROJECT_VERSION_DRIFT:{key}')
 result={'state':'PASS' if not find else 'FAIL','version':VERSION,'findings':find}
 if a.output:
  a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
 print(json.dumps(result,ensure_ascii=False,sort_keys=True));return 0 if not find else 2
if __name__=='__main__':raise SystemExit(main())
