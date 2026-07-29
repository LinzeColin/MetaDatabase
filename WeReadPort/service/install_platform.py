#!/usr/bin/env python3
"""Prepare or activate an immutable, rollback-capable WeRead Port v0.0.0.1.9 systemd release."""
from __future__ import annotations
import argparse, base64, json, os, pathlib, pwd, re, secrets, shutil, subprocess, sys, tempfile, time, urllib.request
VERSION = "0.0.0.1.9"
TASKPACK_VERSION = f"v{VERSION}"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{3,160}$")
UNITS = (
    "weread-port-platform.service", "weread-port-import-worker.service", "weread-port-edge-bridge.service",
    "weread-port-platform-health.timer", "weread-port-platform-backup.timer",
    "weread-port-facts-sync.timer", "weread-port-private-database-backup.timer",
    "weread-port-r2-oci-backup.timer",
)
REQUIRED_DEPLOY_KEYS = (
    "WRP_TASKPACK_VERSION","WRP_RELEASE_COMMIT","WRP_OVH_RELEASE_ID","WRP_SITES_PROJECT_ID",
    "WRP_ADMIN_BASE_URL","WRP_ADMIN_ACCOUNT_IDS","WRP_EDGE_BRIDGE_HOST","WRP_EDGE_BRIDGE_PORT",
    "WRP_SESSION_PEPPER","WRP_CREDENTIAL_PEPPER","WRP_KEYRING_JSON","WRP_ACTIVE_KEY_ID","WRP_INTERNAL_PROXY_SECRET",
    "WRP_R2_ENDPOINT","WRP_R2_BUCKET","WRP_R2_ACCESS_KEY_ID","WRP_R2_SECRET_ACCESS_KEY",
    "WRP_PRIMARY_OBJECT_PREFIX","WRP_PRIVATE_DATABASE_BACKUP_PREFIX",
    "WRP_GOOGLE_CLIENT_ID","WRP_GOOGLE_CLIENT_SECRET","WRP_GITHUB_CLIENT_ID","WRP_GITHUB_CLIENT_SECRET","WRP_NOTION_CLIENT_ID","WRP_NOTION_CLIENT_SECRET",
    "WRP_PRIVATE_DATABASE_CLIENT_PATH","WRP_PRIVATE_DATABASE_CLIENT_SHA256","WRP_PRIVATE_DATABASE_AREA","WRP_PRIVATE_DATABASE_DOMAIN","WRP_PRIVATE_DATABASE_GH_TOKEN","WRP_PRIVATE_DATABASE_R2_BACKUP_TARGET","WRP_R2_RCLONE_SOURCE","WRP_OCI_RCLONE_TARGET",
)

def root_path(root: pathlib.Path, absolute: str) -> pathlib.Path: return root / absolute.lstrip("/")
def read_env(path: pathlib.Path) -> dict[str,str]:
 values={}
 if path.is_file():
  for raw in path.read_text(encoding="utf-8").splitlines():
   line=raw.strip()
   if line and not line.startswith("#") and "=" in line:
    key,value=line.split("=",1); values[key.strip()]=value.strip()
 return values

def atomic_write(path: pathlib.Path, text: str, mode: int=0o600) -> None:
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(prefix=f".{path.name}.",suffix=".tmp",dir=path.parent)
 try:
  with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as handle:
   handle.write(text); handle.flush(); os.fsync(handle.fileno())
  os.chmod(name,mode); os.replace(name,path)
 finally:
  try: os.unlink(name)
  except FileNotFoundError: pass

def update_env(path: pathlib.Path, template: pathlib.Path, updates: dict[str,str], *, generate_secrets: bool) -> dict[str,str]:
 if not path.exists(): path.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(template,path)
 values=read_env(path); generated={}
 if generate_secrets:
  for key in ("WRP_SESSION_PEPPER","WRP_CREDENTIAL_PEPPER","WRP_INTERNAL_PROXY_SECRET"):
   if not values.get(key): generated[key]=base64.b64encode(secrets.token_bytes(32)).decode("ascii") if key!="WRP_INTERNAL_PROXY_SECRET" else secrets.token_urlsafe(48)
  if not values.get("WRP_KEYRING_JSON"):
   generated["WRP_KEYRING_JSON"]=json.dumps({"k1":base64.b64encode(secrets.token_bytes(32)).decode("ascii")},separators=(",",":")); generated.setdefault("WRP_ACTIVE_KEY_ID","k1")
 merged={**generated,**updates}; lines=path.read_text(encoding="utf-8").splitlines(); out=[]; seen=set()
 for line in lines:
  if "=" in line and not line.lstrip().startswith("#"):
   key=line.split("=",1)[0].strip()
   if key in merged: line=f"{key}={merged[key]}"; seen.add(key)
  out.append(line)
 for key,value in merged.items():
  if key not in seen: out.append(f"{key}={value}")
 atomic_write(path,"\n".join(out).rstrip()+"\n",0o600); return read_env(path)

def copy_release(source_root: pathlib.Path, target: pathlib.Path) -> None:
 if target.exists():
  if not target.is_dir(): raise RuntimeError("RELEASE_PATH_NOT_DIRECTORY")
  shutil.rmtree(target)
 temp=target.with_name(f".{target.name}.tmp-{os.getpid()}")
 if temp.exists(): shutil.rmtree(temp)
 temp.mkdir(parents=True)
 try:
  # The account service reuses the reviewed WeRead normalizer from src/core.
  # Ship that dependency with every immutable service release; copying service/
  # alone would only fail after a real process restart.
  for name in ("service","src/core","package.json","AGENTS.md"):
   src=source_root/name; dst=temp/name
   if src.is_dir(): shutil.copytree(src,dst,ignore=shutil.ignore_patterns("__pycache__","*.pyc",".DS_Store"))
   else: shutil.copy2(src,dst)
  for script in (temp/"service/scripts").glob("*.py"): script.chmod(0o755)
  temp.replace(target)
 finally:
  if temp.exists(): shutil.rmtree(temp)

def run_preflight(source_root,path,strict,require_paths):
 cmd=[sys.executable,str(source_root/"service/scripts/platform_preflight.py"),"--env-file",str(path)]
 if strict:cmd.append("--strict")
 if require_paths:cmd.append("--require-paths")
 done=subprocess.run(cmd,capture_output=True,text=True,timeout=45,check=False)
 try:payload=json.loads(done.stdout)
 except json.JSONDecodeError as exc: raise RuntimeError("PREFLIGHT_OUTPUT_INVALID") from exc
 payload["exitCode"]=done.returncode; return payload

def wait_for_platform_ready(port: int, timeout_seconds: float = 30.0) -> None:
 deadline=time.monotonic()+timeout_seconds; url=f"http://127.0.0.1:{port}/readyz"
 while time.monotonic()<deadline:
  try:
   with urllib.request.urlopen(url,timeout=3) as response:
    payload=json.loads(response.read(1024*1024).decode("utf-8"))
    if response.status==200 and payload.get("ready") is True: return
  except Exception: pass
  time.sleep(0.5)
 raise RuntimeError("PLATFORM_READY_TIMEOUT")

def validate_identity(commit,ovh,sites):
 if not SHA40.fullmatch(commit): raise RuntimeError("--release-commit 必须是 40 位小写 Git SHA")
 if not SAFE_ID.fullmatch(ovh): raise RuntimeError("--ovh-release-id 无效")
 if not SAFE_ID.fullmatch(sites): raise RuntimeError("--sites-project-id 无效")

def main()->int:
 parser=argparse.ArgumentParser(); parser.add_argument("--root",type=pathlib.Path,default=pathlib.Path("/")); parser.add_argument("--apply",action="store_true")
 parser.add_argument("--release-commit",default=os.environ.get("WRP_RELEASE_COMMIT","")); parser.add_argument("--ovh-release-id",default=os.environ.get("WRP_OVH_RELEASE_ID","")); parser.add_argument("--sites-project-id",default=os.environ.get("WRP_SITES_PROJECT_ID","")); args=parser.parse_args()
 root=args.root.expanduser().resolve(); source_root=pathlib.Path(__file__).resolve().parents[1]
 identity_supplied=bool(args.release_commit or args.ovh_release_id or args.sites_project_id)
 if args.apply or identity_supplied: validate_identity(args.release_commit,args.ovh_release_id,args.sites_project_id)
 release_suffix=(args.release_commit[:12]+"-"+re.sub(r"[^A-Za-z0-9._-]","-",args.ovh_release_id)[:48]) if identity_supplied else "prepared"
 release=root_path(root,f"/opt/weread-port/releases/{VERSION}-{release_suffix}"); current=root_path(root,"/opt/weread-port/current"); env_file=root_path(root,"/etc/weread-port/platform.env"); unit_dir=root_path(root,"/etc/systemd/system"); state=root_path(root,"/var/lib/weread-port")
 copy_release(source_root,release); state.mkdir(parents=True,exist_ok=True,mode=0o700)
 updates={}
 if identity_supplied: updates={"WRP_TASKPACK_VERSION":TASKPACK_VERSION,"WRP_RELEASE_COMMIT":args.release_commit,"WRP_OVH_RELEASE_ID":args.ovh_release_id,"WRP_SITES_PROJECT_ID":args.sites_project_id}
 previous_env_text=env_file.read_text(encoding="utf-8") if env_file.exists() else None
 values=update_env(env_file,source_root/"service/env/weread-port-platform.env.example",updates,generate_secrets=args.apply and root==pathlib.Path("/"))
 unit_dir.mkdir(parents=True,exist_ok=True)
 for unit in sorted((source_root/"service/systemd").iterdir()):
  if unit.is_file(): shutil.copy2(unit,unit_dir/unit.name); (unit_dir/unit.name).chmod(0o644)
 missing=[key for key in REQUIRED_DEPLOY_KEYS if not values.get(key)]
 preflight=run_preflight(source_root,env_file,strict=args.apply and root==pathlib.Path("/"),require_paths=args.apply and root==pathlib.Path("/"))
 activated=False; previous_target=os.readlink(current) if current.is_symlink() else None
 if args.apply and root==pathlib.Path("/"):
  if os.geteuid()!=0: raise PermissionError("--apply 需要 root")
  if missing or preflight.get("status")!="PASS":
   print(json.dumps({"status":"INPUT_REQUIRED","missing":sorted(set(missing)),"preflight":preflight,"environment":str(env_file),"next":"只补齐列出的真实环境输入后重试同一命令；不得改版本或代码"},ensure_ascii=False,indent=2,sort_keys=True)); return 3
  try: pwd.getpwnam("weread-port")
  except KeyError: subprocess.run(["useradd","--system","--home","/var/lib/weread-port","--shell","/usr/sbin/nologin","weread-port"],check=True)
  subprocess.run(["chown","-R","weread-port:weread-port",str(state),str(release)],check=True)
  current.parent.mkdir(parents=True,exist_ok=True); tmp=current.with_name(f".current-{os.getpid()}")
  if tmp.exists() or tmp.is_symlink(): tmp.unlink()
  tmp.symlink_to(pathlib.Path("releases")/release.name); os.replace(tmp,current)
  try:
   subprocess.run(["systemctl","daemon-reload"],check=True); subprocess.run(["systemctl","enable","--now",*UNITS],check=True); subprocess.run(["systemctl","restart","weread-port-platform.service","weread-port-import-worker.service","weread-port-edge-bridge.service"],check=True); wait_for_platform_ready(int(values.get("WRP_SERVICE_PORT","8788"))); subprocess.run(["systemctl","start","weread-port-platform-health.service","weread-port-private-database-backup.service"],check=True); activated=True
  except Exception:
   # The release identity lives in the environment file. Roll it back together
   # with the symlink so /version can never advertise a release that failed.
   if previous_env_text is None:
    try: env_file.unlink()
    except FileNotFoundError: pass
   else: atomic_write(env_file,previous_env_text,0o600)
   if previous_target:
    rollback=current.with_name(f".current-rollback-{os.getpid()}"); rollback.symlink_to(previous_target); os.replace(rollback,current); subprocess.run(["systemctl","daemon-reload"],check=False)
   subprocess.run(["systemctl","try-restart","weread-port-platform.service","weread-port-import-worker.service","weread-port-edge-bridge.service"],check=False)
   raise
 else:
  current.parent.mkdir(parents=True,exist_ok=True)
  if current.is_symlink() or current.is_file(): current.unlink()
  elif current.exists(): shutil.rmtree(current)
  current.symlink_to(pathlib.Path("releases")/release.name)
 print(json.dumps({"status":"ACTIVATED" if activated else "PREPARED","version":TASKPACK_VERSION,"release":str(release),"current":str(current),"environment":str(env_file),"missingDeploymentInputs":sorted(set(missing)),"preflight":preflight,"units":list(UNITS),"nextCommand":None if activated else f"sudo python3 service/install_platform.py --apply --release-commit <40_SHA> --ovh-release-id <ID> --sites-project-id <EXISTING_PROJECT_ID>"},ensure_ascii=False,indent=2,sort_keys=True)); return 0
if __name__=="__main__":
 try: raise SystemExit(main())
 except Exception as exc: print(json.dumps({"status":"FAILED","errorCode":type(exc).__name__,"message":str(exc)},ensure_ascii=False),file=sys.stderr); raise SystemExit(2)
