#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.upstream_inputs import inspect_checkout

STOCK_ROOT = Path('Signal-Lattice') / 'Stock_Skill'



def jdump(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')

def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def clean_env(extra: dict[str,str]|None=None) -> dict[str,str]:
    env = {
        'PATH':os.environ.get('PATH','/usr/bin:/bin'),
        'HOME':tempfile.gettempdir(),
        'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONHASHSEED':'0',
        'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,
        'GIT_TERMINAL_PROMPT':'0','GIT_ASKPASS':'/bin/false','SSH_ASKPASS':'/bin/false',
        'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','PIP_NO_INDEX':'1',
    }
    if extra: env.update(extra)
    return env

def run(cmd: list[str], cwd: Path, timeout: int=120, env: dict[str,str]|None=None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,env=clean_env(env))

def run_bytes(cmd: list[str], cwd: Path, timeout: int=120, env: dict[str,str]|None=None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(cmd,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,env=clean_env(env))

def git(repo: Path, *args: str) -> str:
    cp=run(['git',*args],repo)
    if cp.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {cp.stderr.strip()}")
    return cp.stdout.strip()

def assert_repo(repo: Path, expected: str) -> dict[str,Any]:
    inspection = inspect_checkout(repo, expected)
    if inspection.state != 'PASS':
        raise RuntimeError(f'{repo.name} checkout invalid: {inspection.reason}')
    try:
        origin=git(repo,'remote','get-url','origin')
    except RuntimeError:
        origin=''
    data=inspection.as_dict()
    return {
        'repo':repo.name,
        'expected_commit':expected,
        'actual_commit':data['actual_commit'],
        'root_tree':data['root_tree'],
        'origin':origin,
        'clean':data['clean'],
        'shallow':data['shallow'],
        'object_format':data['object_format'],
        'snapshot_completeness_verified':True,
    }

def list_records(data: Any) -> list[dict[str,Any]]:
    if isinstance(data,list):
        return [x for x in data if isinstance(x,dict)]
    if isinstance(data,dict):
        for key in ('skills','instances','items','entries','registry'):
            val=data.get(key)
            if isinstance(val,list): return [x for x in val if isinstance(x,dict)]
        # values may be records keyed by id
        vals=[v for v in data.values() if isinstance(v,dict)]
        if vals and len(vals) >= 2: return vals
    raise ValueError('No record list found')

def first(d: dict[str,Any], keys: tuple[str,...]) -> Any:
    for k in keys:
        v=d.get(k)
        if v not in (None,'',[]): return v
    return None

def normalize_source(v: Any) -> str:
    if isinstance(v,str): return v
    if isinstance(v,dict):
        return str(first(v,('id','name','source','registry','path')) or json.dumps(v,sort_keys=True))
    return str(v or 'unknown')

def candidate_entry(repo:Path, rec:dict[str,Any], slug:str, source:str)->Path:
    raw=first(rec,('entry','entrypoint','path','skill_path','file','skill_file'))
    options=[]
    if isinstance(raw,str):
        p=Path(raw)
        options += [p, Path('CodexSkills')/p]
        if p.suffix=='': options += [p/'SKILL.md', Path('CodexSkills')/p/'SKILL.md']
    options += [
        Path('CodexSkills/registry/codex')/slug/'SKILL.md',
        Path('CodexSkills/registry')/source/slug/'SKILL.md',
        Path('CodexSkills')/slug/'SKILL.md',
    ]
    for p in options:
        if (repo/p).is_file(): return p
    # conservative exact parent-name search
    matches=[p.relative_to(repo) for p in repo.glob('CodexSkills/**/SKILL.md') if p.parent.name==slug]
    if len(matches)==1: return matches[0]
    raise FileNotFoundError(f'entry unresolved for {source}:{slug}; candidates={matches[:5]}')

def git_object_bytes(repo:Path,obj:str)->bytes:
    cp=run_bytes(['git','cat-file','blob',obj],repo)
    if cp.returncode:
        raise RuntimeError(f'git cat-file blob {obj} failed: {cp.stderr.decode("utf-8","replace").strip()}')
    return cp.stdout


def git_tree(repo:Path, root:Path)->dict[str,Any]:
    cp=run_bytes(['git','ls-tree','-r','-z','--full-tree','HEAD','--',root.as_posix()],repo)
    if cp.returncode:
        raise RuntimeError(cp.stderr.decode('utf-8','replace'))
    entries=[]
    for raw in cp.stdout.split(b'\0'):
        if not raw: continue
        meta,path_raw=raw.split(b'\t',1)
        mode_raw,typ_raw,obj_raw=meta.split(b' ',2)
        mode=mode_raw.decode('ascii')
        typ=typ_raw.decode('ascii')
        obj=obj_raw.decode('ascii')
        try:
            path=path_raw.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise RuntimeError('NON_UTF8_GIT_PATH_FORBIDDEN') from exc
        if typ == 'commit' or mode == '160000':
            raise RuntimeError(f'SUBMODULE_ENTRY_FORBIDDEN:{path}')
        if typ != 'blob':
            raise RuntimeError(f'UNSUPPORTED_GIT_ENTRY:{typ}:{mode}:{path}')
        if mode not in {'100644','100755','120000'}:
            raise RuntimeError(f'UNSUPPORTED_GIT_MODE:{mode}:{path}')
        content=git_object_bytes(repo,obj)
        fp=repo/path
        if mode == '120000':
            kind='symlink'
            if not fp.is_symlink():
                raise RuntimeError(f'WORKTREE_SYMLINK_MISMATCH:{path}')
        else:
            kind='executable' if mode == '100755' else 'regular'
            if not fp.is_file() or fp.is_symlink():
                raise RuntimeError(f'WORKTREE_FILE_MISMATCH:{path}')
        entries.append({
            'path':path,
            'mode':mode,
            'kind':kind,
            'git_blob_sha1':obj,
            'size':len(content),
            'sha256':hashlib.sha256(content).hexdigest(),
        })
    entries.sort(key=lambda x:x['path'])
    if not entries: raise RuntimeError(f'empty tracked tree: {root}')
    return {
        'root':root.as_posix(),
        'file_count':len(entries),
        'files':entries,
        'tree_sha256':sha_bytes(jdump(entries)),
        'hash_basis':'GIT_CANONICAL_BLOB_BYTES_NOT_WORKTREE_DEREFERENCE',
        'submodules_allowed':False,
    }

REQUIRED_SLUGS={'verifier','teleiosis','persona-distiller-group','persona-distiller','ui-ux-pro-max'}
REQUIRED_KEYWORDS=('product','design','ui','ux','web','test','verify','review','security','database','data','architecture','deploy','backup','restore','status','systemd','sre','git','context','dual-plane','package','release','python','api','cloudflare','persona','teleiosis','stock','equity','quant','finance')
N_A_KEYWORDS=('ppt','slide','video','image-generation','payroll','dingtalk','tender','pet','wechat-read','notion-only')

def classify(slug:str,desc:str)->tuple[str,str]:
    text=(slug+' '+desc).lower()
    if slug in REQUIRED_SLUGS: return 'ASSURANCE_REQUIRED','named mandatory method source'
    if any(k in text for k in N_A_KEYWORDS): return 'NOT_APPLICABLE','outside frozen Signal Lattice scope'
    if any(k in text for k in REQUIRED_KEYWORDS): return 'SUPPORTING','applies to product, engineering, data, security, UI, operations, or assurance'
    return 'CONDITIONAL','retained for explicit route-time applicability check'

def license_refs(repo:Path, root:Path)->list[dict[str,Any]]:
    candidates=[]
    for base in (repo/root, repo):
        if base.exists():
            for p in base.iterdir():
                if p.is_file() and re.match(r'(?i)^(license|copying|notice)(\..*)?$',p.name): candidates.append(p)
    uniq=[]; seen=set()
    for p in candidates:
        rp=p.relative_to(repo).as_posix()
        if rp in seen: continue
        seen.add(rp); uniq.append({'path':rp,'size':p.stat().st_size,'sha256':sha_file(p)})
    return uniq

def build_agent_matrix(repo:Path,expected_instances:int,expected_unique:int)->dict[str,Any]:
    idx=repo/'CodexSkills/index.json'
    data=json.loads(idx.read_text())
    records=list_records(data)
    rows=[]
    for i,rec in enumerate(records):
        slug=str(first(rec,('slug','name','id','skill')) or f'unknown-{i}')
        source=normalize_source(first(rec,('source','registry','origin','provider')))
        desc=str(first(rec,('description','summary','purpose')) or '')
        entry=candidate_entry(repo,rec,slug,source)
        root=entry.parent
        tree=git_tree(repo,root)
        cls,reason=classify(slug,desc)
        rows.append({
            'instance_index':i,
            'instance_id':f'{source}:{slug}:{entry.as_posix()}',
            'slug':slug,'source':source,'description':desc,'entry':entry.as_posix(),
            'entry_sha256':sha_file(repo/entry),'classification':cls,'classification_reason':reason,
            'runtime_agent_allowed':False,'runtime_llm_allowed':False,
            'full_tree':tree,'license_refs':license_refs(repo,root)
        })
    unique=len({r['slug'] for r in rows})
    if len(rows)!=expected_instances or unique!=expected_unique:
        raise RuntimeError(f'index count mismatch {len(rows)}/{unique}, expected {expected_instances}/{expected_unique}')
    return {'index_path':'CodexSkills/index.json','index_sha256':sha_file(idx),'instance_count':len(rows),'unique_slug_count':unique,'rows':rows}

def stock_records(data:Any)->list[dict[str,Any]]:
    return list_records(data)

def build_stock_matrix(repo:Path,expected_stock_skills:int)->dict[str,Any]:
    reg=repo/STOCK_ROOT/'REGISTRY.json'
    data=json.loads(reg.read_text())
    recs=stock_records(data)
    rows=[]
    for i,rec in enumerate(recs):
        slug=str(first(rec,('slug','name','id','skill_id')) or f'unknown-{i}')
        raw=first(rec,('path','root','project_path','directory','skill_path'))
        options=[]
        if isinstance(raw,str): options.append(Path(raw))
        options += [STOCK_ROOT/slug]
        root=None
        for p in options:
            if (repo/p).is_dir(): root=p;break
        if root is None:
            # try id/name directory matching
            matches=[p.relative_to(repo) for p in (repo/STOCK_ROOT).iterdir() if p.is_dir() and p.name.lower()==slug.lower()]
            if len(matches)==1: root=matches[0]
        if root is None: raise FileNotFoundError(f'stock skill root unresolved: {slug} raw={raw}')
        tree=git_tree(repo,root)
        version=first(rec,('version','latest_version','release_version'))
        release=first(rec,('release_sha256','release_hash','artifact_sha256','sha256'))
        rows.append({'index':i,'slug':slug,'root':root.as_posix(),'version':version,'declared_release_sha256':release,'record':rec,'full_tree':tree,'license_refs':license_refs(repo,root)})
    if len(rows)!=expected_stock_skills: raise RuntimeError(f'stock registry count {len(rows)} != {expected_stock_skills}')
    return {'registry_path':(STOCK_ROOT/'REGISTRY.json').as_posix(),'registry_sha256':sha_file(reg),'skill_count':len(rows),'rows':rows}

def find_first(repo:Path, rels:list[str])->Path|None:
    for rel in rels:
        p=repo/rel
        if p.is_file(): return p
    return None

def validator(name:str,repo:Path,rels:list[str],args:list[str]|None=None,timeout:int=120)->dict[str,Any]:
    p=find_first(repo,rels)
    if p is None:
        return {'name':name,'state':'NOT_PRESENT','allowed':True,'candidate_paths':rels}
    if p.suffix=='.py': cmd=[sys.executable,p.name]+(args or [])
    elif p.suffix=='.sh' or os.access(p,os.X_OK): cmd=['bash',p.name]+(args or [])
    else: return {'name':name,'state':'UNSUPPORTED_FILE','path':p.relative_to(repo).as_posix()}
    cp=run(cmd,p.parent,timeout=timeout,env={'PYTHONPATH':str(repo)})
    out={'name':name,'path':p.relative_to(repo).as_posix(),'argv':cmd,'exit_code':cp.returncode,
         'stdout_sha256':sha_bytes(cp.stdout.encode()),'stderr_sha256':sha_bytes(cp.stderr.encode()),
         'stdout_tail':cp.stdout[-2000:],'stderr_tail':cp.stderr[-2000:]}
    out['state']='PASS' if cp.returncode==0 else 'FAIL'
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True);ap.add_argument('--agent',type=Path,required=True);ap.add_argument('--meta',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    baseline=json.loads((a.root/'machine/facts/upstream_baseline.json').read_text())
    agent_cfg=baseline['agent_database']; meta_cfg=baseline['meta_database']
    expected_agent_commit=agent_cfg['commit']; expected_meta_commit=meta_cfg['commit']
    repo_receipts={'agent':assert_repo(a.agent,expected_agent_commit),'meta':assert_repo(a.meta,expected_meta_commit)}
    agent_matrix=build_agent_matrix(a.agent,int(agent_cfg['skill_instance_count']),int(agent_cfg['unique_slug_count']))
    stock_matrix=build_stock_matrix(a.meta,int(meta_cfg['stock_skill_count']))
    validators=[
      validator('persona_group_registry',a.agent,[
        'CodexSkills/registry/codex/persona-distiller-group/scripts/validate_group.py',
        'CodexSkills/registry/codex/persona-distiller-group/scripts/validate_registry.py']),
      validator('persona_distiller_selfcheck',a.agent,[
        'CodexSkills/registry/codex/persona-distiller/scripts/validate.py',
        'CodexSkills/registry/codex/persona-distiller/scripts/self_check.py']),
      validator('teleiosis_strict',a.agent,[
        'CodexSkills/registry/codex/teleiosis/scripts/verify_self.py',
        'CodexSkills/registry/codex/teleiosis/scripts/verify-self.py',
        'CodexSkills/registry/codex/teleiosis/scripts/verify_self.sh'],['--strict']),
      validator('verifier_selftest',a.agent,[
        'CodexSkills/registry/codex/verifier/scripts/run_selftest.py',
        'CodexSkills/registry/codex/verifier/scripts/run_self_test.py'],['--repeat','2']),
      validator('stock_registry',a.meta,[
        (STOCK_ROOT/'scripts/validate_registry.py').as_posix(),
        (STOCK_ROOT/'validate_registry.py').as_posix()])
    ]
    invalid=[v for v in validators if v['state']!='PASS']
    if invalid:
        partial={'schema_version':'1.0.0','state':'BLOCKED','validators':validators,'reason':'REQUIRED_UPSTREAM_VALIDATOR_NOT_PASS'}
        partial['receipt_sha256']=sha_bytes(jdump(partial))
        (a.output/'upstream_seal.blocked.json').write_text(json.dumps(partial,ensure_ascii=False,indent=2,sort_keys=True))
        raise RuntimeError('one or more required upstream validators are missing or failed')
    files={
      'agent_skill_matrix.json':agent_matrix,
      'stock_skill_matrix.json':stock_matrix,
      'validator_receipts.json':{'validators':validators},
      'repo_receipts.json':repo_receipts,
    }
    hashes={}
    for name,obj in files.items():
        b=json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True).encode(); (a.output/name).write_bytes(b); hashes[name]=sha_bytes(b)
    seal={
      'schema_version':'1.0.0','state':'PASS','agent_commit':expected_agent_commit,'meta_commit':expected_meta_commit,
      'agent_root_tree':repo_receipts['agent']['root_tree'],'meta_root_tree':repo_receipts['meta']['root_tree'],
      'skill_instance_count':agent_matrix['instance_count'],'unique_slug_count':agent_matrix['unique_slug_count'],
      'stock_skill_count':stock_matrix['skill_count'],'artifact_sha256':hashes,
      'runtime_agent_dependency':0,'runtime_llm_token_budget':0,'upstream_write_allowed':False,
      'validator_states':{v['name']:v['state'] for v in validators},
      'limitations':['validator state NOT_PRESENT is explicit and is not converted to PASS'],
    }
    seal['receipt_sha256']=sha_bytes(jdump(seal))
    (a.output/'upstream_seal.json').write_text(json.dumps(seal,ensure_ascii=False,indent=2,sort_keys=True))
    # Verify self hash
    chk=json.loads((a.output/'upstream_seal.json').read_text()); rec=chk.pop('receipt_sha256'); assert sha_bytes(jdump(chk))==rec
    print(json.dumps({'state':'PASS','receipt_sha256':seal['receipt_sha256'],'skill_instances':agent_matrix['instance_count'],'stock_skills':stock_matrix['skill_count'],'validators':seal['validator_states']},ensure_ascii=False))
if __name__=='__main__': main()
