#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Private-Database 统一存取客户端 —— 免 clone、免本地落地。

本仓 LinzeColin/Private-Database 是全仓全项目统一私有数据存储。任何系统（KMFA 前端、
OpenAIDatabase、MetaDatabase 各项目）都用本客户端跨仓读写数据，底层走 GitHub REST API
（经 `gh` 复用登录态），**永不 git clone 本仓、不在本地留数据副本**。

用法：
    python3 private_db_client.py ingest <区> <本地文件> --domain 财务   # 上传业务文件（算 sha256+追加账本）
    python3 private_db_client.py put    <区> <区内路径> <本地文件>       # 直接写/覆盖任意路径
    python3 private_db_client.py get    <区> <区内路径> <输出文件>       # 按需下载单文件
    python3 private_db_client.py list   <区> [前缀]                      # 列目录
    python3 private_db_client.py delete <区> <区内路径>                  # 删除
    python3 private_db_client.py verify <区>                            # 用 manifest 全量核对

区 ∈ Private-KMDatabase | Private-AgentDatabase | Private-MetaDatabase
"""
import argparse, base64, hashlib, json, os, re, subprocess, sys, tempfile
from datetime import date

REPO = "LinzeColin/Private-Database"
BRANCH = "main"
AREAS = {"Private-KMDatabase", "Private-AgentDatabase", "Private-MetaDatabase"}
MAX_BYTES = 95 * 1024 * 1024  # GitHub 100MB 硬限，留余量

# ── 红线：凭据类文件名 / 内容 / 运行库，永不入仓 ──
DENY_NAME = re.compile(r"(^\.env|\.env\.|\.key$|\.pem$|\.p12$|\.pfx$|id_rsa|"
                       r"token|secret|cookie|credential|(^|[_-])auth\.json$|session\.json$)", re.I)
DENY_DB = re.compile(r"\.(sqlite3?|db)$", re.I)
DENY_CONTENT = re.compile(rb"(-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|"
                          rb"ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{10,}\.eyJ)")


# 连接级瞬时错误（连接未建立，重试绝对安全）
_TRANSIENT = re.compile(r"dial tcp|i/o timeout|operation timed out|connection reset|"
                        r"connection refused|EOF|TLS handshake timeout|no such host", re.I)


def _gh(args, input_bytes=None, raw_out=None, check=True, retries=4):
    """调用 gh api；连接级瞬时错误自动重试（指数退避 1/2/4/8s）。
    raw_out 给定则把原始响应字节写入该文件路径。"""
    cmd = ["gh", "api"] + args
    last = ""
    for attempt in range(retries):
        if raw_out is not None:
            with open(raw_out, "wb") as f:
                p = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
            err = p.stderr.decode("utf-8", "replace")
            if p.returncode == 0:
                return 0
        else:
            p = subprocess.run(cmd, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            err = p.stderr.decode("utf-8", "replace")
            if p.returncode == 0:
                return p.stdout
        last = err
        if _TRANSIENT.search(err) and attempt < retries - 1:
            import time
            time.sleep(2 ** attempt)
            continue
        break
    if check:
        raise RuntimeError(last)
    return p.returncode if raw_out is not None else p.stdout


def _check_area(area):
    if area not in AREAS:
        sys.exit(f"✗ 未知数据区 {area}；应为 {sorted(AREAS)}")


def _redline(local, data):
    name = os.path.basename(local)
    if DENY_NAME.search(name):
        sys.exit(f"✗ 红线拒绝（凭据类文件名）：{name}")
    if DENY_DB.search(name):
        sys.exit(f"✗ 红线拒绝（运行库 *.sqlite/*.db 不入仓）：{name}")
    if len(data) > MAX_BYTES:
        sys.exit(f"✗ 单文件 {len(data)/1e6:.1f}MB > 95MB 硬限；需 Git LFS 或分片，见 README 天花板")
    if DENY_CONTENT.search(data[:1_000_000]):
        sys.exit(f"✗ 红线拒绝（内容命中密钥/令牌模式）：{name}")


def _get_meta(path):
    """返回文件的 {sha,size,...}；不存在返回 None。"""
    try:
        out = _gh([f"repos/{REPO}/contents/{path}?ref={BRANCH}"], check=True)
        return json.loads(out)
    except RuntimeError as e:
        if "Not Found" in str(e) or "404" in str(e):
            return None
        raise


def put(area, relpath, local, message=None, _data=None):
    _check_area(area)
    data = _data if _data is not None else open(local, "rb").read()
    _redline(local or relpath, data)
    path = f"{area}/{relpath}"
    meta = _get_meta(path)
    body = {"message": message or f"data({area}): put {relpath}",
            "content": base64.b64encode(data).decode(), "branch": BRANCH}
    if meta:  # 覆盖：带旧 sha 乐观并发
        if meta.get("sha") and _blob_sha(data) == meta["sha"]:
            print(f"= 幂等跳过（内容一致）：{path}")
            return path
        body["sha"] = meta["sha"]
    _gh(["--method", "PUT", f"repos/{REPO}/contents/{path}", "--input", "-"],
        input_bytes=json.dumps(body).encode())
    print(f"✓ {'覆盖' if meta else '新建'} {path}  ({len(data)/1e6:.2f}MB)")
    return path


def _blob_sha(data):
    """git blob sha1（用于幂等比对）。"""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def get(area, relpath, out):
    _check_area(area)
    path = f"{area}/{relpath}"
    _gh([f"repos/{REPO}/contents/{path}?ref={BRANCH}", "-H", "Accept: application/vnd.github.raw"],
        raw_out=out)
    print(f"✓ 下载 {path} -> {out}  ({os.path.getsize(out)/1e6:.2f}MB)")


def delete(area, relpath, message=None):
    _check_area(area)
    path = f"{area}/{relpath}"
    meta = _get_meta(path)
    if not meta:
        sys.exit(f"✗ 不存在：{path}")
    body = {"message": message or f"data({area}): delete {relpath}", "branch": BRANCH, "sha": meta["sha"]}
    _gh(["--method", "DELETE", f"repos/{REPO}/contents/{path}", "--input", "-"],
        input_bytes=json.dumps(body).encode())
    print(f"✓ 删除 {path}")


def list_(area, prefix=""):
    _check_area(area)
    path = f"{area}/{prefix}".rstrip("/")
    try:
        out = _gh([f"repos/{REPO}/contents/{path}?ref={BRANCH}"])
        for e in json.loads(out):
            sz = f"{e['size']/1e6:.2f}MB" if e["type"] == "file" else "dir"
            print(f"  {e['type']:4} {sz:>10}  {e['path']}")
    except RuntimeError as e:
        sys.exit(f"✗ {e}")


def ingest(area, local, domain, batch=None):
    """上传业务文件：算 sha256、内容寻址入 objects/、追加 manifest。KMFA 前端上传走这条。"""
    _check_area(area)
    data = open(local, "rb").read()
    _redline(local, data)
    sha = hashlib.sha256(data).hexdigest()
    name = os.path.basename(local)
    relobj = f"objects/{sha[:2]}/{sha}_{name}"
    path = f"{area}/{relobj}"
    if _get_meta(path):
        print(f"= 对象已存在，幂等跳过上传：{relobj}")
    else:
        put(area, relobj, None, message=f"data({area}): ingest {name}", _data=data)
    _append_manifest(area, {
        "sha256": sha, "original_name": name, "size_bytes": len(data),
        "domain": domain, "batch": batch or str(date.today()),
        "object_path": relobj, "ingested_at": str(date.today())})
    print(f"✓ 入库完成 domain={domain} sha256={sha[:12]}… {name}")


def _append_manifest(area, record, retries=4):
    mpath = f"{area}/manifest.jsonl"
    for attempt in range(retries):
        meta = _get_meta(mpath)
        cur = b""
        if meta:
            with tempfile.NamedTemporaryFile(delete=False) as tf:
                tmp = tf.name
            _gh([f"repos/{REPO}/contents/{mpath}?ref={BRANCH}", "-H", "Accept: application/vnd.github.raw"],
                raw_out=tmp)
            cur = open(tmp, "rb").read()
            os.unlink(tmp)
            # 幂等：同 sha256 已在账本则不重复追加
            if record["sha256"].encode() in cur:
                print("= manifest 已含该 sha256，不重复追加")
                return
        new = cur + (b"" if (not cur or cur.endswith(b"\n")) else b"\n") + \
              json.dumps(record, ensure_ascii=False).encode() + b"\n"
        body = {"message": f"data({area}): manifest += {record['sha256'][:12]}",
                "content": base64.b64encode(new).decode(), "branch": BRANCH}
        if meta:
            body["sha"] = meta["sha"]
        try:
            _gh(["--method", "PUT", f"repos/{REPO}/contents/{mpath}", "--input", "-"],
                input_bytes=json.dumps(body).encode())
            return
        except RuntimeError as e:
            if ("409" in str(e) or "does not match" in str(e)) and attempt < retries - 1:
                continue  # 并发撞车，重取重试（串行化）
            raise
    sys.exit("✗ manifest 追加多次撞车失败，请重试")


def verify(area):
    _check_area(area)
    mpath = f"{area}/manifest.jsonl"
    meta = _get_meta(mpath)
    if not meta:
        print(f"（{area} 无 manifest.jsonl，跳过）"); return
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tmp = tf.name
    _gh([f"repos/{REPO}/contents/{mpath}?ref={BRANCH}", "-H", "Accept: application/vnd.github.raw"], raw_out=tmp)
    ok = miss = 0
    for line in open(tmp, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if _get_meta(f"{area}/{r['object_path']}"):
            ok += 1
        else:
            miss += 1; print(f"  ✗ 缺对象：{r['object_path']}")
    os.unlink(tmp)
    print(f"{area}: 账本 {ok+miss} 条，对象在仓 {ok}，缺 {miss}")


def main():
    ap = argparse.ArgumentParser(description="Private-Database 统一存取客户端（免 clone）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest"); p.add_argument("area"); p.add_argument("local"); p.add_argument("--domain", required=True); p.add_argument("--batch")
    p = sub.add_parser("put"); p.add_argument("area"); p.add_argument("relpath"); p.add_argument("local")
    p = sub.add_parser("get"); p.add_argument("area"); p.add_argument("relpath"); p.add_argument("out")
    p = sub.add_parser("delete"); p.add_argument("area"); p.add_argument("relpath")
    p = sub.add_parser("list"); p.add_argument("area"); p.add_argument("prefix", nargs="?", default="")
    p = sub.add_parser("verify"); p.add_argument("area")
    a = ap.parse_args()
    if a.cmd == "ingest": ingest(a.area, a.local, a.domain, a.batch)
    elif a.cmd == "put": put(a.area, a.relpath, a.local)
    elif a.cmd == "get": get(a.area, a.relpath, a.out)
    elif a.cmd == "delete": delete(a.area, a.relpath)
    elif a.cmd == "list": list_(a.area, a.prefix)
    elif a.cmd == "verify": verify(a.area)


if __name__ == "__main__":
    main()
