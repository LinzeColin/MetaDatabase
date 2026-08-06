#!/usr/bin/env python3
"""部署完之后，去**生产**回读一遍（v0.0.0.8 / G5）。

## 为什么不能拿本地结果冒充

`deploy_to_production.sh` 自己已经验了不少（鉴权路由、下载包逐字节一致、
仓=主机=镜像三份一致）。这个脚本补的是另一件事：**用户真正拿到的那几样东西**。

而「用户拿到的」和「服务器上有的」不是一回事，这个项目已经栽过两次：

  · 一次是判据绿了但指错了文件——同一道门在两处布局给出相反结论，
    它查的那个路径只有本地有。
  · 一次是**从来没人打开过最终那个 zip**：47 道门全在验暂存目录，
    改成回读自验证之后第一次跑就抓到 283 个中文名乱码。

所以这里只问四件用户会撞上的事，而且全部从生产读：

  1. `/health` 说的版本 —— 安装页拿它当"需要的版本"
  2. **下载页真正下发的那个包**里 manifest 的版本，以及它含不含取数器
  3. 平台能力表 —— 界面照着它画按钮
  4. 安装页与资料库页面**服务器真正吐出来的字节**

## 一个陷阱：别从公网量

`social-archive.linzezhang.com` 挡在 Cloudflare Access 后面。
不带登录态去 curl，拿到的是 302 到登录页的 143 字节，
于是每一条断言都会"失败"——而页面本身好端端的。
2026-08-06 我就是这么量了一次，四条全报 False。
**所以这个脚本从 origin（127.0.0.1:18765）量**，那是 Access 放行之后
Owner 真正拿到的那一份。

## 用法

    python3 scripts/verify_production_deployment.py            # 默认 linze-ovh
    python3 scripts/verify_production_deployment.py --host xxx
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REMOTE = r'''
set -e
TOKEN=$(sudo cat /opt/social-archive/runtime/secrets/social_archive_api_token)
B=http://127.0.0.1:18765
curl -s -m 20 "$B/health" > /tmp/sa_health.json
curl -s -m 20 -H "Authorization: Bearer $TOKEN" "$B/v1/accounts" > /tmp/sa_accounts.json
curl -s -m 60 -o /tmp/sa_ext.zip "$B/downloads/social-archive-extension.zip"
curl -s -m 20 "$B/extension-install" > /tmp/sa_install.html
curl -s -m 20 "$B/assets/app.js" > /tmp/sa_app.js
# **apps/pwa/ 下每一个文件都要比**，不是只比我这次改过的那两个。
# 只比手挑的几个，等于「我记得改了什么就验什么」——而漏掉的那些
# 恰恰是没人注意、于是也没人发现它没上线的。
mkdir -p /tmp/sa_pwa
for f in app.js extension-install.html index.html styles.css sw.js manifest.webmanifest favicon.svg; do
  curl -s -m 20 -o "/tmp/sa_pwa/$f" "$B/assets/$f" || true
done
python3 - <<'PY'
import json, re, zipfile, hashlib
out = {}
out["health"] = json.load(open("/tmp/sa_health.json"))
accounts = json.load(open("/tmp/sa_accounts.json"))
out["platforms"] = {p["platform"]: {"sync_supported": p["sync_supported"],
                                    "server_handled": p.get("server_handled")}
                    for p in accounts.get("supported_platforms", [])}
z = zipfile.ZipFile("/tmp/sa_ext.zip")
names = z.namelist()
out["package"] = {
    "manifest_version": json.loads(z.read("manifest.json"))["version"],
    "file_count": len(names),
    "has_bilibili_reader": any("bilibili-reader" in n for n in names),
    "sha256": hashlib.sha256(open("/tmp/sa_ext.zip","rb").read()).hexdigest(),
}
html = open("/tmp/sa_install.html", encoding="utf-8").read()
body = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
back = re.search(r'class="button secondary"[^>]*href="([^"]+)"', body)
out["install_page"] = {
    "bytes": len(html),
    "says_overwrite_same_folder": "覆盖进你原来那个插件文件夹" in body,
    "warns_new_extension_id": "新的插件 ID" in body,
    "compares_versions": "requiredVersion" in body,
    "back_href": back.group(1) if back else "",
    "stale_versions": sorted(set(re.findall(r"v?0\.0\.0\.\d", body))),
}
app = open("/tmp/sa_app.js", encoding="utf-8").read()
import os
out["served_sha256"] = {}
for name in os.listdir("/tmp/sa_pwa"):
    blob = open(os.path.join("/tmp/sa_pwa", name), "rb").read()
    # 空文件多半是那条路由压根没有，别把它当成"内容不一致"
    out["served_sha256"][name] = hashlib.sha256(blob).hexdigest() if blob else ""
pv = re.search(r'const PRODUCT_VERSION = "([0-9.]+)"', app)
out["library_page"] = {
    "product_version": pv.group(1) if pv else "",
    "knows_bilibili_failure_codes": "BILIBILI_NOT_LOGGED_IN" in app,
}
print(json.dumps(out, ensure_ascii=False))
PY
rm -rf /tmp/sa_pwa
rm -f /tmp/sa_health.json /tmp/sa_accounts.json /tmp/sa_ext.zip /tmp/sa_install.html /tmp/sa_app.js
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="部署后去生产回读")
    parser.add_argument("--host", default="linze-ovh")
    parser.add_argument("--out", default="evidence/G5/DEPLOYED_AND_READ_BACK.json")
    args = parser.parse_args()

    want = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    done = subprocess.run(["ssh", "-o", "ConnectTimeout=20", args.host, REMOTE],
                          capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        print(json.dumps({"status": "FAIL", "error_code": "REMOTE_PROBE_FAILED",
                          "detail": (done.stderr or done.stdout)[-500:]},
                         ensure_ascii=False, indent=2))
        return 2
    try:
        measured = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print(json.dumps({"status": "FAIL", "error_code": "UNREADABLE_PROBE",
                          "detail": done.stdout[-500:]}, ensure_ascii=False, indent=2))
        return 2

    problems: list[str] = []
    if measured["health"].get("version") != want:
        problems.append(f"生产 /health 说 {measured['health'].get('version')}，仓里是 {want}")
    # **后台在不在跑。** 2026-08-06 一次被打断的部署留下 core-api 起来了、
    # core-worker 卡在 Created 没启动——而 /health 由 api 提供，照样回 ok。
    # 从外面完全看不出后台没在跑，任务只会静静积压。
    # 这一条要在**部署当场**问，那正是它最容易发生的时刻。
    worker = measured["health"].get("worker") or {}
    if not worker:
        problems.append("生产的 /health 里没有 worker 这一块——这一版还没带上心跳，"
                        "或者部署的不是这一版")
    elif not worker.get("alive"):
        problems.append(f"**后台 worker 没在跑**：{worker.get('note') or worker}"
                        "——接口是好的，但同步任务不会有人处理")
    package = measured["package"]
    if package["manifest_version"] != want:
        problems.append(
            f"**下载页下发的插件包还是 {package['manifest_version']}**，仓里是 {want}"
            "——他下载下来装上去，安装页会立刻又说「你装的是旧版」")
    if not package["has_bilibili_reader"]:
        problems.append("**下发的包里没有 bilibili-reader.js** —— B 站收藏夹读不了")
    bilibili = measured["platforms"].get("bilibili") or {}
    if not bilibili.get("sync_supported"):
        problems.append("生产的平台能力表里 bilibili 还是不能同步")
    if bilibili.get("server_handled"):
        problems.append("**bilibili 被标成服务端处理** —— 那条路永远拿不到它需要的登录态"
                        "（国内平台 Cookie 不出浏览器），会被从能跑通的浏览器路上踢走")
    page = measured["install_page"]
    if not page["says_overwrite_same_folder"]:
        problems.append("安装页不再讲「覆盖进你原来那个插件文件夹」——换文件夹装会变成第二个插件")
    if not page["warns_new_extension_id"]:
        problems.append("安装页没有「会变成新的插件 ID」那条警告")
    if not page["compares_versions"]:
        problems.append("安装页不比版本——装着旧版的人会被无限弹回来")
    if page["back_href"] != "/":
        problems.append(f"安装页的返回按钮指向 {page['back_href']!r}（曾经指向 /home，那是 404）")
    stale = [v for v in page["stale_versions"] if v.lstrip("v") != want]
    if stale:
        problems.append(f"安装页上还印着旧版本号：{stale}")
    library = measured["library_page"]
    if library["product_version"] != want:
        problems.append(
            f"**资料库判兼容用的 PRODUCT_VERSION 是 {library['product_version']}**，仓里是 {want}"
            "——它会把刚更新好的插件判成不兼容，人又回到「去更新」的循环里")
    if not library["knows_bilibili_failure_codes"]:
        problems.append("资料库页面不认识 B 站的失败码，会显示「我们没能记录下原因」")

    # **服务器发的页面，和仓里这一份是不是同一份字节。**
    #
    # 2026-08-06 这一条是被一次假绿逼出来的：我改了资料库页面、不升版本就部署，
    # 部署因磁盘不足**中止了**，而这个脚本报 PASS——因为它当时只比版本，
    # 而版本本来就还是上一次部署留下的那个。**「PASS」当时的意思是
    # 「上一版好好的」，我却读成了「我这次的改动上线了」。**
    #
    # 不升版本部署是这一版新立的规矩（界面文案不该逼人重装插件），
    # 而它的代价正是：**版本号不再能证明你的改动到没到**。所以改成比字节。
    import hashlib as _hashlib
    served_map = measured.get("served_sha256") or {}
    pwa_files = sorted(item for item in (ROOT / "apps/pwa").iterdir() if item.is_file())
    # **一个都没比到 = 这一条失效了**，不是"通过"
    if len(served_map) < 3:
        problems.append(f"只取到 {len(served_map)} 个页面指纹——**这不是通过**，"
                        "是这一条的射程失效了")
    for path in pwa_files:
        name = path.name
        local = _hashlib.sha256(path.read_bytes()).hexdigest()
        served = served_map.get(name, "")
        if not served:
            problems.append(f"没能取到生产上 {name} 的指纹——这一条没验到，不算通过")
        elif served != local:
            problems.append(
                f"**生产上的 {name} 不是仓里这一份**（仓 {local[:12]}… / 线上 {served[:12]}…）"
                "——多半是这次部署没成，而版本号看不出来")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "task": "G5",
        "host": args.host,
        "expected_version": want,
        "measured_from_production": measured,
        "problems": problems,
        "why_origin_not_public": (
            "资料库域名挡在 Cloudflare Access 后面，不带登录态 curl 只会拿到 302 到登录页的"
            "143 字节，四条断言会全报 False 而页面其实好端端的（2026-08-06 实测踩过）。"
            "所以从 origin 量——那是 Access 放行之后 Owner 真正拿到的那一份。"),
        "what_this_does_not_prove": (
            "没有证明 Owner 自己的 B 站收藏夹读得出来——那要他本人的登录态，"
            "发生在他自己的浏览器里。这里证明的是：他要用到的每一样东西，"
            "生产上都是新的那一份。"),
    }
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
