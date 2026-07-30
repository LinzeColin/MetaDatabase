#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path

def digest(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def build(root:Path,out:Path)->Path:
 env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME','PIP_INDEX_URL','PIP_EXTRA_INDEX_URL'}}
 env.update({'PYTHONHASHSEED':'0','SOURCE_DATE_EPOCH':'315532800','TZ':'UTC','LC_ALL':'C.UTF-8','LANG':'C.UTF-8','PIP_NO_INDEX':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1','PIP_NO_CACHE_DIR':'1'})
 r=subprocess.run([os.sys.executable,'-m','pip','wheel','.', '--no-deps','--no-build-isolation','--no-index','-w',str(out)],cwd=root,env=env,text=True,capture_output=True,timeout=180)
 if r.returncode:raise SystemExit('WHEEL_BUILD_FAILED:'+r.stderr[-500:])
 wheels=list(out.glob('signal_lattice-*.whl'))
 if len(wheels)!=1:raise SystemExit('WHEEL_COUNT_INVALID')
 return wheels[0]
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
 with tempfile.TemporaryDirectory() as t:
  d1=Path(t)/'a';d2=Path(t)/'b';d1.mkdir();d2.mkdir();w1=build(root,d1);w2=build(root,d2)
  same=w1.read_bytes()==w2.read_bytes()
  if not same:raise SystemExit('NON_REPRODUCIBLE_WHEEL')
  a.output_dir.mkdir(parents=True,exist_ok=True);dest=a.output_dir/w1.name;shutil.copy2(w1,dest)
  receipt={'schema_version':'1.0.0','state':'PASS','wheel':dest.name,'sha256':digest(dest),'size':dest.stat().st_size,'build_count':2,'byte_identical':True,'network_required':False}
  a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
  print(json.dumps(receipt,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
