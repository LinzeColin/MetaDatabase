#!/usr/bin/env python3
"""S-003 passive security audit (safe, read-only, non-intrusive) + active-scan
scope for the authorized isolated run.

Passive checks run safely against production: transport/framing headers, TLS,
CORS reflection, cookie flags, server/tech fingerprint disclosure, error-body
information leakage, and PII in public responses. ACTIVE testing (fuzzing at
scale, authz probing, injection) is documented but NOT executed — it requires
the Run Contract's authorized isolated clone.
"""
import argparse
import json
import re
import socket
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = {"user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
REQUIRED_HEADERS = {
    "strict-transport-security": lambda v: "max-age" in v and int(re.search(r"max-age=(\d+)", v).group(1)) >= 31536000,
    "content-security-policy": lambda v: "default-src" in v and "frame-ancestors" in v,
    "x-content-type-options": lambda v: v.lower()=="nosniff",
    "x-frame-options": lambda v: v.upper() in ("DENY","SAMEORIGIN"),
    "referrer-policy": lambda v: bool(v),
    "permissions-policy": lambda v: bool(v),
}
FINGERPRINT_HEADERS = ["server","x-powered-by","x-aspnet-version","x-generator"]

def fetch(base, path, extra=None):
    hdr = dict(UA) 
    if extra: hdr.update(extra)
    r = urllib.request.Request(base+path, headers=hdr)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, {k.lower():v for k,v in resp.headers.items()}, resp.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        return e.code, {k.lower():v for k,v in e.headers.items()}, e.read().decode("utf-8","replace")

def run(base, host):
    checks = []
    def add(cid, desc, ok, detail):
        checks.append({"id":cid,"desc":desc,"verdict":"PASS" if ok else "FAIL","detail":detail}); print(json.dumps(checks[-1]))

    # S3-1 required security headers on root + an API route
    for label, path in [("root","/"),("api","/health")]:
        _, h, _ = fetch(base, path)
        missing = [k for k,pred in REQUIRED_HEADERS.items() if k not in h or not pred(h[k])]
        add(f"S3-1-{label}", f"security headers on {label}", not missing, {"missing_or_weak":missing})

    # S3-2 no tech-stack fingerprint leakage (Cloudflare 'server' is acceptable/expected)
    _, h, _ = fetch(base, "/")
    leaked = {k:h[k] for k in FINGERPRINT_HEADERS if k in h and h[k].lower() not in ("cloudflare",)}
    add("S3-2","no server/framework version fingerprint", not leaked, {"fingerprint":leaked})

    # S3-3 CORS not reflecting arbitrary origins with credentials
    _, h, _ = fetch(base, "/v1/publication/meta", {"origin":"https://evil.example"})
    acao = h.get("access-control-allow-origin","")
    acac = h.get("access-control-allow-credentials","")
    ok = not (acao=="https://evil.example" and acac.lower()=="true")
    add("S3-3","CORS does not reflect arbitrary origin with credentials", ok, {"acao":acao,"acac":acac})

    # S3-4 error bodies never leak stack traces / engine errors (fuzz a few)
    leaks_found = {}
    for p in ["/v1/entities?q="+("A"*5000), "/v1/scoring/relationship/not-a-uuid/explanation",
              "/v1/explore", "/v1/nonexistent-route"]:
        code, _, body = fetch(base, p)
        bad = [t for t in ["Traceback",'File "',"SQLITE_","at Object.","cloudflare-internal",".mjs:","stack"] if t in body]
        if bad: leaks_found[p]=bad
    add("S3-4","no stack/engine leak in error bodies", not leaks_found, {"leaks":leaks_found})

    # S3-5 no PII in public score explanation
    code, _, body = fetch(base, "/v1/scoring/relationship/dc4d6660-3a52-508d-ae10-c762395e7bf7/explanation")
    email = bool(re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", body))
    add("S3-5","no PII/email in public score explanation", not email, {"email_present":email})

    # S3-6 TLS: modern protocol + valid cert
    tls_ok, tls_detail = True, {}
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=host) as s:
            s.settimeout(10); s.connect((host,443))
            tls_detail = {"version":s.version(),"cipher":s.cipher()[0]}
            tls_ok = s.version() in ("TLSv1.2","TLSv1.3")
    except Exception as e:
        tls_ok, tls_detail = False, {"error":str(e)}
    add("S3-6","TLS >= 1.2 with valid cert", tls_ok, tls_detail)

    verdict = "PASS" if all(c["verdict"]=="PASS" for c in checks) else "FAIL"
    active_scope = {
        "status":"NOT_RUN_requires_authorization",
        "authorized_isolated_only":[
            "input fuzzing at scale (search, explore, saved-view bodies)",
            "authz/IDOR probing on user-state resources with a dedicated low-priv account",
            "injection testing (SQL/NoSQL/template) against the isolated clone",
            "rate-limit / DoS resilience probing with an abort owner",
        ],
        "run_contract":"docs/37_ISOLATED_RETEST_SUITE.md",
    }
    return {"suite":"S-003-passive-security","base":base,"ran_at":datetime.now(timezone.utc).isoformat(),
            "passive_checks":checks,"passive_verdict":verdict,"active_scan":active_scope}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://eei.linzezhang.com")
    ap.add_argument("--host", default="eei.linzezhang.com")
    a = ap.parse_args()
    out = run(a.base, a.host)
    print("\n=== S-003 PASSIVE VERDICT:", out["passive_verdict"], "===")
    import os; os.makedirs("out",exist_ok=True); open("out/s003_security.json","w").write(json.dumps(out,indent=2))
