"""离线测试夹具：本地起一个小 http.server，不访问任何外网。"""
import datetime as dt
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run  # noqa: E402


def page(body: str, head: str = "") -> bytes:
    return f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>" \
           f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>t</title>{head}</head>" \
           f"<body>{body}</body></html>".encode("utf-8")


def routes() -> dict:
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return {
        "/ok": page("<main><h1>欢迎 正常页面</h1><p>英超 概率 63%</p>"
                    "<a href='/ok2'>第二页</a> <a href='/nohead'>只支持 GET</a>"
                    "<table><tr><td>行一</td></tr></table>"
                    "<button id='chg' onclick=\"document.body.insertAdjacentHTML('beforeend','<p>已变化</p>')\">改变</button>"
                    "<button id='noop'>无反应</button></main>"),
        "/ok2": page("<main><h1>第二页</h1></main>"),
        "/undef": page("<main><h1>价格</h1><p>当前价 undefined 元</p></main>"),
        "/deadlink": page("<main><h1>有死链</h1><a href='/missing-page'>坏链</a></main>"),
        "/wide": page("<main><h1>太宽</h1><div style='width:2000px;height:20px;background:#ccc'>宽</div></main>"),
        "/fresh": page(f"<main><h1>今日</h1><p>报告日期：{today}</p></main>"),
        "/stale": page("<main><h1>旧</h1><p>报告日期：2020-01-01</p></main>"),
        "/jserr": page("<main><h1>脚本错误</h1></main><script>throw new Error('boom-e2e')</script>"),
        "/fetch500": page("<main><h1>后台挂了</h1></main><script>fetch('/api/boom')</script>"),
        "/nohead": page("<main><h1>只支持 GET</h1></main>"),
    }


JSONS = {
    "/api/items.json": {"data": {"items": [1, 2, 3]}},
    "/api/empty.json": {"data": {"items": []}},
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, body: bytes, ctype: str, head_only: bool):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _handle(self, head_only: bool):
        path = self.path.split("?")[0]
        if path == "/nohead" and head_only:
            return self._send(405, b"", "text/plain", True)
        if path == "/api/boom":
            return self._send(500, b"boom", "text/plain", head_only)
        if path in JSONS:
            return self._send(200, json.dumps(JSONS[path]).encode(), "application/json", head_only)
        r = routes()
        if path in r:
            return self._send(200, r[path], "text/html; charset=utf-8", head_only)
        return self._send(404, page("<h1>404</h1>"), "text/html; charset=utf-8", head_only)

    def do_GET(self):
        self._handle(False)

    def do_HEAD(self):
        self._handle(True)


@pytest.fixture(scope="session")
def base_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()


@pytest.fixture(autouse=True)
def stub_axe(tmp_path, monkeypatch):
    """离线：用桩 axe 代替真实 axe-core，只验证注入与 critical 计数逻辑。"""
    p = tmp_path / "axe-stub.js"
    p.write_text("window.axe={run:()=>Promise.resolve({violations:[{id:'stub-critical',impact:'critical',nodes:[{}]},"
                 "{id:'stub-minor',impact:'minor',nodes:[{}]}]})};", encoding="utf-8")
    monkeypatch.setenv("E2E_AXE_JS", str(p))


@pytest.fixture
def go(tmp_path, base_url):
    """go(spec_dict_without_base_url) -> (退出码, report.json 内容, 输出目录)"""
    def _go(spec: dict, name: str = "t.yaml"):
        spec = {"project": "测试项目", "base_url": base_url, "viewports": ["desktop"], **spec}
        f = tmp_path / name
        f.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
        out = tmp_path / "out"
        rc = run.main([str(f), "--out", str(out)])
        dirs = sorted(out.iterdir()) if out.exists() else []
        rep = json.loads((dirs[-1] / "report.json").read_text(encoding="utf-8")) if dirs and (dirs[-1] / "report.json").exists() else None
        return rc, rep, (dirs[-1] if dirs else None)
    return _go
