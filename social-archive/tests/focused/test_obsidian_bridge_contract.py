from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import httpx

from social_archive.destinations import DestinationRegistry
from social_archive.models import CaptureRequest


def _secret(path: Path, value: str) -> str:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
    return str(path)


def _factory(transport: httpx.BaseTransport):
    return lambda **kwargs: httpx.Client(transport=transport, **kwargs)


def test_obsidian_plugin_is_token_bound_loopback_only_and_markdown_only():
    root = Path(__file__).parents[2] / "apps/obsidian-plugin"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    source = (root / "main.js").read_text(encoding="utf-8")
    assert manifest["version"] == "0.0.0.4"
    assert manifest["isDesktopOnly"] is True
    assert 'listen(this.settings.port, "127.0.0.1"' in source
    assert "this.settings.port = DEFAULT_SETTINGS.port" in source
    assert "timingSafeEqual(suppliedBytes, expectedBytes)" in source
    assert 'request.url !== "/vault"' in source
    assert 'startsWith("text/markdown")' in source
    assert "safeBaseFolder" in source
    assert 'target.endsWith(".md")' in source
    assert "launchd" not in source.lower()
    assert "20 * 1024 * 1024" in source


def test_obsidian_plugin_rejects_escape_and_returns_noop_for_identical_markdown():
    plugin = Path(__file__).parents[2] / "apps/obsidian-plugin/main.js"
    harness = r'''
const assert = require("assert");
const Module = require("module");
const files = new Map();
const folders = new Set();
class Plugin { constructor(app) { this.app = app; } }
class PluginSettingTab {}
class Setting {}
class Notice {}
class TFile { constructor(path) { this.path = path; } }
function normalizePath(value) {
  return String(value).replace(/\\/g, "/").replace(/\/+/g, "/").replace(/^\/+/, "");
}
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === "obsidian") return { Plugin, PluginSettingTab, Setting, Notice, normalizePath, TFile };
  return originalLoad.call(this, request, parent, isMain);
};
const SocialArchivePlugin = require(process.argv[1]);
const vault = {
  getAbstractFileByPath(path) {
    if (files.has(path)) return new TFile(path);
    if (folders.has(path)) return {};
    return null;
  },
  async createFolder(path) { folders.add(path); },
  async read(file) { return files.get(file.path); },
  async modify(file, body) { files.set(file.path, body); },
  async create(path, body) { files.set(path, body); }
};
function response() {
  return {
    status: null,
    body: null,
    writeHead(status) { this.status = status; },
    end(body) { this.body = body; }
  };
}
function request({ method = "PUT", url = "/vault", headers = {}, chunks = [] }) {
  return {
    method,
    url,
    headers,
    async *[Symbol.asyncIterator]() { for (const chunk of chunks) yield chunk; }
  };
}
(async () => {
  const plugin = new SocialArchivePlugin({ vault });
  plugin.settings = { baseFolder: "Social Archive", token: "abc", port: 27123, maxBytes: 20 * 1024 * 1024 };
  assert.strictEqual(plugin.authorized({ headers: { authorization: "Bearer abc" } }), true);
  assert.strictEqual(plugin.authorized({ headers: { authorization: "Bearer ab" } }), false);
  assert.strictEqual(plugin.safeTarget("nested%2Fnote.md"), "Social Archive/nested/note.md");
  assert.throws(() => plugin.safeTarget("..%2Fescape.md"), /路径/);
  plugin.settings.baseFolder = "../escape";
  assert.throws(() => plugin.safeTarget("note.md"), /保存目录/);
  plugin.settings.baseFolder = "Social Archive";
  let result = response();
  await plugin.handle(request({ headers: { authorization: "Bearer abc", "content-type": "application/json" } }), result);
  assert.strictEqual(result.status, 415);
  plugin.settings.maxBytes = 2;
  result = response();
  await plugin.handle(request({ headers: { authorization: "Bearer abc", "content-type": "text/markdown" }, chunks: [Buffer.from("abc")] }), result);
  assert.strictEqual(result.status, 413);
  plugin.settings.maxBytes = 20 * 1024 * 1024;
  const path = plugin.safeTarget("note.md");
  const headers = { authorization: "Bearer abc", "content-type": "text/markdown", "x-social-archive-path": "note.md" };
  result = response();
  await plugin.handle(request({ headers, chunks: [Buffer.from("first")] }), result);
  assert.deepStrictEqual(JSON.parse(result.body), { status: "done", path });
  result = response();
  await plugin.handle(request({ headers, chunks: [Buffer.from("first")] }), result);
  assert.deepStrictEqual(JSON.parse(result.body), { status: "noop", path });
  assert.deepStrictEqual(await plugin.writeMarkdown(path, "second"), { status: "done", path });
  assert.strictEqual(files.get(path), "second");
  console.log("ok");
})().catch(error => { console.error(error); process.exit(1); });
'''
    result = subprocess.run(
        ["node", "-e", harness, str(plugin)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_server_vault_obsidian_export_probes_writes_and_returns_noop(settings, store, service, tmp_path):
    vault_root = tmp_path / "vault"
    configured = replace(settings, obsidian_vault_root=vault_root)
    registry = DestinationRegistry(configured, store)
    probe = registry.probe("obsidian")
    assert probe["state"] == "connected"
    captured = service.capture(
        CaptureRequest(
            platform="generic_web",
            url="https://unit.test/obsidian-vault",
            title="Vault 导出",
            text="Vault 正文",
            requested_levels=["L0", "L1"],
            destination_ids=["social_archive"],
        )
    )
    first = registry.export("obsidian", captured.content_id, job_id="obsidian-vault-first")
    second = registry.export("obsidian", captured.content_id, job_id="obsidian-vault-repeat")
    target = Path(str(first["path"])).resolve()
    assert first["status"] == "done"
    assert second["status"] == "noop"
    assert target.is_relative_to((vault_root / "Social Archive").resolve())
    assert "Vault 正文" in target.read_text(encoding="utf-8")
    assert sorted(item["status"] for item in store.list_destination_receipts(content_id=captured.content_id)) == ["done", "noop"]


def test_server_rest_obsidian_export_uses_markdown_put_and_noop_binding(settings, store, service, tmp_path):
    configured = replace(
        settings,
        obsidian_rest_url="https://127.0.0.1:27124",
        obsidian_rest_token_file=_secret(tmp_path / "obsidian.token", "secret"),
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/":
            return httpx.Response(200, json={"versions": {"self": "4.1.3"}})
        if request.method == "GET" and request.url.path == "/vault/":
            return httpx.Response(200, json={"files": []})
        assert request.method == "PUT"
        assert request.headers["Authorization"] == "Bearer secret"
        assert request.headers["Content-Type"] == "text/markdown; charset=utf-8"
        assert request.url.path.startswith("/vault/Social Archive/")
        assert request.url.path.endswith(".md")
        return httpx.Response(204)

    captured = service.capture(
        CaptureRequest(
            platform="generic_web",
            url="https://unit.test/obsidian-rest",
            title="REST 导出",
            text="REST 正文",
            requested_levels=["L0", "L1"],
            destination_ids=["social_archive"],
        )
    )
    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    assert registry.probe("obsidian")["authorized"] is True
    requests.clear()
    first = registry.export("obsidian", captured.content_id, job_id="obsidian-rest-first")
    second = registry.export("obsidian", captured.content_id, job_id="obsidian-rest-repeat")
    assert first["status"] == "done"
    assert second["status"] == "noop"
    assert len(requests) == 1
