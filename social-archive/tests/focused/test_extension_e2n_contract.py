import json
import subprocess
from pathlib import Path


def _extension_root() -> Path:
    return Path(__file__).parents[2] / "apps/browser-extension"


def test_extension_has_e2n_like_surfaces_and_one_primary_action():
    root = _extension_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["version"] == "0.0.0.4"
    assert manifest["action"]["default_popup"] == "popup.html"
    assert manifest["side_panel"]["default_path"] == "sidepanel.html"
    assert manifest["options_page"] == "options.html"
    required = {
        "runtime-config.json", "popup.html", "popup.js", "popup.css", "sidepanel.html", "sidepanel.js",
        "options.html", "options.js", "options.css", "shared.js", "background.js",
        "content/fab.js", "content/extract.js",
    }
    assert required <= {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}
    all_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in root.rglob("*.*"))
    for phrase in ("保存到我的档案馆", "读取当前列表", "任务中心", "destinationIds", "needs_user_action"):
        assert phrase in all_text


def test_extension_is_cloud_first_but_preserves_explicit_local_dev_and_obsidian_boundaries():
    root = _extension_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    runtime = json.loads((root / "runtime-config.json").read_text(encoding="utf-8"))
    assert runtime["endpoint"] == "https://social-archive-api.linzezhang.com"
    assert runtime["library_url"] == "https://social-archive.linzezhang.com"
    assert runtime["managed"] is True
    assert manifest["host_permissions"] == ["https://social-archive-api.linzezhang.com/*"]
    assert "http://127.0.0.1:27123/*" in manifest["optional_host_permissions"]
    assert "http://127.0.0.1:8765/*" in manifest["optional_host_permissions"]
    assert "http://127.0.0.1:18765/*" in manifest["optional_host_permissions"]
    assert "<all_urls>" not in manifest.get("host_permissions", [])


def test_extension_auth_and_privacy_boundaries_are_explicit():
    root = _extension_root()
    scripts = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.js"))
    forbidden = ("document.cookie", "chrome.cookies", "scrollTo(", "scrollBy(", "eval(", "new Function(")
    assert not any(token in scripts for token in forbidden)
    assert "chrome.permissions.request" in scripts
    assert "/v1/pairing/exchange" in scripts
    assert "只在你点击" in (root / "options.html").read_text(encoding="utf-8") or "不会进入" in (root / "options.html").read_text(encoding="utf-8")


def test_extension_default_destinations_and_archive_levels():
    root = _extension_root()
    shared = (root / "shared.js").read_text(encoding="utf-8")
    background = (root / "background.js").read_text(encoding="utf-8")
    assert 'destinationIds: ["social_archive"]' in shared
    assert '["L0", "L1", "L3"]' in background
    assert "/v1/captures/batch" in background
    assert "/v1/extension/bootstrap" in (root / "popup.js").read_text(encoding="utf-8")
    options = (root / "options.js").read_text(encoding="utf-8")
    sidepanel = (root / "sidepanel.js").read_text(encoding="utf-8")
    assert "/v1/destinations/${encodeURIComponent(id)}/probe" in options
    assert "last_checked_at" in options
    assert "/v1/destinations/receipts" in sidepanel
    assert "obsidianLocalEnabled" in background


def test_extension_has_first_run_shortcut_and_visible_connection_summary():
    root = _extension_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["commands"]) >= {"save-current-page", "open-task-center"}
    assert manifest["commands"]["save-current-page"]["suggested_key"]["mac"] == "Command+Shift+A"
    background = (root / "background.js").read_text(encoding="utf-8")
    popup_html = (root / "popup.html").read_text(encoding="utf-8")
    popup_js = (root / "popup.js").read_text(encoding="utf-8")
    assert "options.html?onboarding=1" in background
    assert "chrome.commands.onCommand.addListener" in background
    assert 'id="connectionSummary"' in popup_html
    assert "已授权来源" in popup_js and "已连接目的地" in popup_js and "待处理" in popup_js


def test_extension_exposes_unambiguous_authorization_vocabulary_and_accessibility():
    root = _extension_root()
    shared = (root / "shared.js").read_text(encoding="utf-8")
    for token in ("authorized", "unauthorized", "unsupported", "已授权", "未授权", "暂不支持"):
        assert token in shared
    css = "\n".join((root / name).read_text(encoding="utf-8") for name in ("popup.css", "options.css", "sidepanel.css"))
    assert "focus-visible" in css
    assert "prefers-reduced-motion" in css


def test_destination_counter_does_not_double_count_builtins_and_unconnected_targets_are_disabled():
    root = Path(__file__).parents[2] / "apps/browser-extension"
    popup = (root / "popup.js").read_text(encoding="utf-8")
    options = (root / "options.js").read_text(encoding="utf-8")
    assert 'item.destination_id !== "social_archive"' in popup
    assert 'const checkboxDisabled = id === "social_archive" || !connected' in options
    assert 'serverItems.get(id)?.state === "connected"' in options
    assert 'item.destination_id !== "social_archive"' in options


def test_advanced_api_override_does_not_silently_rewrite_library_destination():
    options = (_extension_root() / "options.js").read_text(encoding="utf-8")
    assert 'libraryUrl: config.libraryUrl' in options
    assert 'libraryUrl: endpoint, token: ""' not in options


def test_extension_renders_status_metadata_and_retries_a_failed_destination_receipt():
    root = _extension_root()
    options = (root / "options.js").read_text(encoding="utf-8")
    sidepanel = (root / "sidepanel.js").read_text(encoding="utf-8")
    assert "last_checked_at" in options and "latency_ms" in options and "last_message_zh" in options
    assert "最后检查：" in options and "延迟未测量" in options
    assert "/v1/destinations/receipts/${encodeURIComponent(job.receipt_id)}/retry" in sidepanel
    assert "SA_RETRY_LOCAL_OBSIDIAN" in sidepanel
    assert 'retry.classList.toggle("hidden", !["needs_user_action", "failed"].includes(state))' in sidepanel


def test_local_obsidian_bridge_is_pinned_to_the_plugin_loopback_origin():
    root = _extension_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    shared = (root / "shared.js").read_text(encoding="utf-8")
    background = (root / "background.js").read_text(encoding="utf-8")
    options = (root / "options.js").read_text(encoding="utf-8")
    html = (root / "options.html").read_text(encoding="utf-8")
    assert 'const OBSIDIAN_LOOPBACK_URL = "http://127.0.0.1:27123"' in shared
    assert "normalizeObsidianLoopbackUrl" in shared
    assert '`${SA.OBSIDIAN_LOOPBACK_URL}/vault`' in background
    assert "config.obsidianLocalUrl.replace" not in background
    assert "obsidianLoopbackUrl" in options
    assert 'const origin = `${SA.OBSIDIAN_LOOPBACK_URL}/*`' in options
    assert 'id="obsidianUrl"' in html and "readonly" in html
    assert manifest["optional_host_permissions"].count("http://127.0.0.1:27123/*") == 1


def test_shared_config_normalizes_a_tampered_obsidian_bridge_address():
    source = _extension_root() / "shared.js"
    harness = r'''
const assert = require("assert");
const fs = require("fs");
let saved = null;
global.chrome = {
  runtime: { getURL: () => "chrome-extension://fixture/runtime-config.json" },
  storage: {
    local: {
      async get(defaults) { return { ...defaults, obsidianLocalUrl: "http://127.0.0.1:8765" }; },
      async set(value) { saved = value; }
    }
  }
};
global.fetch = async () => ({ ok: false });
eval(fs.readFileSync(process.argv[1], "utf8"));
(async () => {
  const current = await SA.getConfig();
  assert.strictEqual(current.obsidianLocalUrl, "http://127.0.0.1:27123");
  await SA.setConfig({ obsidianLocalUrl: "https://example.test", destinationIds: ["obsidian"] });
  assert.strictEqual(saved.obsidianLocalUrl, "http://127.0.0.1:27123");
  assert.deepStrictEqual(saved.destinationIds, ["social_archive", "obsidian"]);
  console.log("ok");
})().catch(error => { console.error(error); process.exit(1); });
'''
    result = subprocess.run(["node", "-e", harness, str(source)], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_chrome_local_obsidian_retry_writes_a_safe_paired_receipt():
    background = _extension_root() / "background.js"
    harness = r'''
const assert = require("assert");
const fs = require("fs");
const path = require("path");
let messageHandler = null;
let stored = {
  endpoint: "https://api.test",
  libraryUrl: "https://library.test",
  token: "paired-token",
  destinationIds: ["social_archive", "obsidian"],
  obsidianLocalEnabled: true,
  obsidianLocalUrl: "http://127.0.0.1:27123",
  obsidianLocalToken: "local-token"
};
const calls = [];
const event = () => ({ addListener() {} });
global.chrome = {
  runtime: {
    getURL: value => value === "runtime-config.json" ? "chrome-extension://fixture/runtime-config.json" : value,
    onInstalled: event(),
    onStartup: event(),
    onMessage: { addListener(handler) { messageHandler = handler; } }
  },
  storage: {
    local: {
      async get(defaults) { return { ...defaults, ...stored }; },
      async set(value) { stored = { ...stored, ...value }; }
    }
  },
  contextMenus: { removeAll: async () => {}, create: () => {}, onClicked: event() },
  scripting: { executeScript: async () => {} },
  tabs: { onUpdated: event(), query: async () => [{ id: 1, url: "https://example.test/" }], create: async () => {} },
  permissions: { onAdded: event(), contains: async () => true },
  commands: { onCommand: event() },
  sidePanel: { setPanelBehavior: async () => {}, open: async () => {} },
  action: { setBadgeBackgroundColor: async () => {}, setBadgeText: async () => {} }
};
global.importScripts = (...names) => {
  for (const name of names) eval(fs.readFileSync(path.join(path.dirname(process.argv[1]), name), "utf8"));
};
global.fetch = async (url, options = {}) => {
  calls.push([String(url), options]);
  if (String(url) === "chrome-extension://fixture/runtime-config.json") {
    return { ok: true, status: 200, text: async () => JSON.stringify({ endpoint: "https://api.test", library_url: "https://library.test" }) };
  }
  if (String(url).endsWith("/v1/library/cnt_fixture/markdown")) {
    return { ok: true, status: 200, text: async () => "# fixture\n" };
  }
  if (String(url) === "http://127.0.0.1:27123/vault") {
    assert.strictEqual(options.headers.Authorization, "Bearer local-token");
    assert.strictEqual(options.headers["Content-Type"], "text/markdown; charset=utf-8");
    return {
      ok: true,
      status: 200,
      json: async () => ({ status: "done", path: "Social Archive/generic_web/retried.md" }),
      text: async () => JSON.stringify({ status: "done", path: "Social Archive/generic_web/retried.md" })
    };
  }
  if (String(url).endsWith("/v1/destinations/obsidian-local/receipts")) {
    const body = JSON.parse(options.body);
    assert.deepStrictEqual(body, {
      content_id: "cnt_fixture",
      status: "done",
      remote_path: "Social Archive/generic_web/retried.md"
    });
    assert.strictEqual(options.headers.get("Authorization"), "Bearer paired-token");
    return { ok: true, status: 202, text: async () => JSON.stringify({ status: "done", receipt_id: "rcpt_fixture" }) };
  }
  throw new Error("unexpected fetch " + url);
};
eval(fs.readFileSync(process.argv[1], "utf8"));
function send(message) {
  return new Promise(resolve => {
    const keep = messageHandler(message, {}, resolve);
    assert.strictEqual(keep, true);
  });
}
(async () => {
  const result = await send({
    type: "SA_RETRY_LOCAL_OBSIDIAN",
    contentId: "cnt_fixture",
    remotePath: "../../must-not-escape.md"
  });
  assert.deepStrictEqual(result, { ok: true, status: "done" });
  assert.strictEqual(calls.filter(([url]) => url === "http://127.0.0.1:27123/vault").length, 1);
  console.log("ok");
})().catch(error => { console.error(error); process.exit(1); });
'''
    result = subprocess.run(["node", "-e", harness, str(background)], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
