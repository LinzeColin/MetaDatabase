#!/usr/bin/env python3
"""Fail-closed production black-box smoke for WeRead Port v0.0.0.1.9."""
from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
MAX_BYTES = 2 * 1024 * 1024
EXPECTED_APP_VERSION = "v0.0.0.1.9"
EXPECTED_SKILL_VERSION = "1.0.4"
EXPECTED_BUSINESS_SCHEMA_VERSION = "2.0.0"
EXPECTED_BUSINESS_LINES = {"public-trust","identity-access","account-storage","cross-device-sync","provider-imports","weread-wide-sync","analytics-recommendations","legacy-migration","release-supply-chain","operations-recovery","facts-backup"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{3,160}$")

def origin(value: str) -> str:
    parsed=urlparse(value.strip().rstrip("/"))
    if parsed.scheme!="https" or not parsed.netloc or parsed.username or parsed.password or parsed.path not in {"","/"} or parsed.query or parsed.fragment: raise ValueError("生产网址必须是无凭据 HTTPS origin")
    return f"https://{parsed.netloc}"

def required(name: str, value: str, pattern: re.Pattern[str]) -> str:
    value=value.strip()
    if not pattern.fullmatch(value): raise ValueError(f"缺少或无效的 {name}")
    return value

def fetch(url: str, *, method="GET", body=None, headers=None, timeout=15.0):
    started=time.monotonic(); request_headers={"User-Agent":"WeReadPort-Smoke/0.0.0.1.9","Accept":"application/json, text/html;q=0.9"}; request_headers.update(headers or {})
    request=Request(url,data=body,method=method,headers=request_headers)
    try:
        with urlopen(request,timeout=timeout) as response:
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES: raise RuntimeError("response_too_large")
            return int(response.status),{k.lower():v for k,v in response.headers.items()},raw,round((time.monotonic()-started)*1000,2)
    except HTTPError as error:
        return int(error.code),{k.lower():v for k,v in error.headers.items()},error.read(MAX_BYTES+1),round((time.monotonic()-started)*1000,2)

def parse_json(raw: bytes, label: str):
    try: return json.loads(raw.decode("utf-8"))
    except Exception as exc: raise RuntimeError(f"{label}_non_json") from exc

def add(checks,name,status,latency,passed,detail=""): checks.append({"name":name,"status":status,"latencyMs":latency,"pass":bool(passed),"detail":detail[:400]})

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("origin"); parser.add_argument("--timeout",type=float,default=15.0); parser.add_argument("--output")
    parser.add_argument("--expected-commit",default=os.environ.get("WRP_RELEASE_COMMIT","")); parser.add_argument("--expected-ovh-release-id",default=os.environ.get("WRP_OVH_RELEASE_ID","")); parser.add_argument("--expected-edge-deployment-id",default=os.environ.get("WRP_EDGE_DEPLOYMENT_ID","")); args=parser.parse_args()
    base=origin(args.origin); commit=required("expected commit",args.expected_commit,SHA40); ovh=required("expected OVH release ID",args.expected_ovh_release_id,SAFE_ID); edge=required("expected edge deployment ID",args.expected_edge_deployment_id,SAFE_ID)
    expected={"taskpackVersion":EXPECTED_APP_VERSION,"releaseCommit":commit,"ovhReleaseId":ovh,"edgeDeploymentId":edge}; checks=[]
    status,headers,raw,latency=fetch(base+"/healthz",timeout=args.timeout); health=parse_json(raw,"health"); add(checks,"liveness",status,latency,status==200 and health.get("status")=="ALIVE",str(health.get("status")))
    status,headers,raw,latency=fetch(base+"/readyz",timeout=args.timeout); readiness=parse_json(raw,"readyz"); account=(readiness.get("checks") or {}).get("accountPlatformService") or {}; actual=account.get("releaseIdentity") or {}
    readiness_ok=status==200 and readiness.get("status")=="READY" and (readiness.get("checks") or {}).get("staticAssets",{}).get("ready") is True and account.get("ready") is True and actual==expected and (readiness.get("checks") or {}).get("businessGovernanceContract",{}).get("schemaVersion")==EXPECTED_BUSINESS_SCHEMA_VERSION
    add(checks,"readiness",status,latency,readiness_ok,f"status={readiness.get('status')};identityMatch={actual==expected}")
    status,headers,raw,latency=fetch(base+"/api/version",timeout=args.timeout); version=parse_json(raw,"version"); identity_ok=all(version.get(k)==v for k,v in expected.items())
    add(checks,"release_identity",status,latency,status==200 and version.get("appVersion")==EXPECTED_APP_VERSION and version.get("sourceSkillVersion")==EXPECTED_SKILL_VERSION and version.get("businessGovernanceSchemaVersion")==EXPECTED_BUSINESS_SCHEMA_VERSION and identity_ok,f"identityMatch={identity_ok}")
    status,headers,raw,latency=fetch(base+"/api/status",timeout=args.timeout); public_status=parse_json(raw,"status"); status_text=raw.decode("utf-8",errors="replace"); safe=all(x not in status_text for x in ["wrk-","Authorization","PRIVATE_DATABASE_TOKEN","R2_SECRET","笔记正文"]); governance=public_status.get("businessGovernance") or {}; lines=governance.get("lines") if isinstance(governance.get("lines"),list) else []; ids={str(x.get("id")) for x in lines if isinstance(x,dict)}; governance_ok=governance.get("schemaVersion")==EXPECTED_BUSINESS_SCHEMA_VERSION and governance.get("graphStatus")=="VALID" and ids==EXPECTED_BUSINESS_LINES and len(lines)==len(EXPECTED_BUSINESS_LINES) and all(x.get("state")!="BLOCKED" for x in lines if isinstance(x,dict)) and public_status.get("dataBoundary",{}).get("businessGovernanceContainsUserContent") is False
    add(checks,"public_status",status,latency,status==200 and public_status.get("status")=="OPERATIONAL" and safe and governance_ok,f"status={public_status.get('status')};lines={len(lines)}")
    for route,required_text in [("/",["一个账户","/assets/"]),("/privacy/",["隐私政策","账户隔离","长期存储","一键导入"]),("/terms/",["使用条款","禁止用途","账户","同步"]),("/status/",["系统状态","/healthz","/readyz","账户与多平台身份","四平台一键导入","画像、热度与推荐"])]:
        status,headers,raw,latency=fetch(base+route,timeout=args.timeout); page=raw.decode("utf-8",errors="replace"); security=all(x in headers for x in ["content-security-policy","referrer-policy","x-content-type-options"]); add(checks,f"page:{route}",status,latency,status==200 and all(x in page for x in required_text) and security,f"security={security}")
    status,headers,raw,latency=fetch(base+"/api/platform/v1/session",headers={"Origin":base,"Sec-Fetch-Site":"same-origin"},timeout=args.timeout); text=raw.decode("utf-8",errors="replace"); add(checks,"account_service_reachable_unauthenticated",status,latency,status==401 and "wrk-" not in text and "Authorization" not in text,f"http={status}")
    status,headers,raw,latency=fetch(base+"/api/weread/gateway",method="POST",body=b'{"api_name":"/user/notebooks"}',headers={"Content-Type":"application/json","Origin":base,"Sec-Fetch-Site":"same-origin"},timeout=args.timeout); text=raw.decode("utf-8",errors="replace"); add(checks,"unauthenticated_proxy_rejected",status,latency,status in {400,401,403} and "wrk-" not in text and "Authorization" not in text,f"http={status}")
    passed=all(x["pass"] for x in checks); result={"status":"PASS" if passed else "FAIL","origin":base,"releaseIdentity":expected,"checks":checks}; rendered=json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n"; print(rendered,end="")
    if args.output: target=Path(args.output); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(rendered,encoding="utf-8")
    return 0 if passed else 1
if __name__=="__main__":
    try: raise SystemExit(main())
    except (ValueError,RuntimeError,URLError,TimeoutError,json.JSONDecodeError) as exc:
        print(json.dumps({"status":"FAIL","error":type(exc).__name__,"message":str(exc)},ensure_ascii=False),file=sys.stderr); raise SystemExit(1)
