import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { recognizePage, SUPPORTED_PLATFORMS } from "../src/page-support.js";

const root = new URL("../", import.meta.url);
const manifest = JSON.parse(await readFile(new URL("manifest.json", root), "utf8"));
const fixture = JSON.parse(
  await readFile(new URL("../../packages/test-fixtures/extension/v1/page_cases.json", root), "utf8"),
);
const sourceFiles = [
  "sidepanel.html",
  "src/page-support.js",
  "src/service-worker.js",
  "src/sidepanel.js",
  "styles/sidepanel.css",
];
const sources = Object.fromEntries(
  await Promise.all(sourceFiles.map(async (path) => [path, await readFile(new URL(path, root), "utf8")])),
);

const failures = [];
const expectedPermissions = ["activeTab", "nativeMessaging", "sidePanel"];
if (manifest.manifest_version !== 3) failures.push("manifest_version");
if (manifest.version !== "0.0.0.1") failures.push("version");
if (manifest.minimum_chrome_version !== "120") failures.push("minimum_chrome_version");
if (JSON.stringify(manifest.permissions) !== JSON.stringify(expectedPermissions)) failures.push("permissions");
if (Object.hasOwn(manifest, "host_permissions")) failures.push("host_permissions");
if (manifest.background?.service_worker !== "src/service-worker.js" || manifest.background?.type !== "module") failures.push("background");
if (manifest.side_panel?.default_path !== "sidepanel.html") failures.push("side_panel");
if (manifest.action?.default_title !== "Open x2n Side Panel") failures.push("action");
if (manifest.content_security_policy?.extension_pages !== "script-src 'self'; object-src 'none';") failures.push("csp");

const publicKey = Buffer.from(manifest.key ?? "", "base64");
const digest = createHash("sha256").update(publicKey).digest().subarray(0, 16).toString("hex");
const extensionId = [...digest].map((nibble) => String.fromCharCode("a".charCodeAt(0) + Number.parseInt(nibble, 16))).join("");
if (extensionId !== "chheapilbdfnpajmlkijppmblnlheeac") failures.push("extension_id");

const forbiddenManifestValues = ["<all_urls>", "cookies", "storage", "scripting", "tabs"];
const renderedManifest = JSON.stringify(manifest);
for (const value of forbiddenManifestValues) if (renderedManifest.includes(value)) failures.push(`forbidden_manifest_${value}`);

for (const [path, source] of Object.entries(sources)) {
  if (/https?:\/\//i.test(source)) failures.push(`remote_source_${path}`);
  if (/\beval\s*\(|new Function\s*\(/.test(source)) failures.push(`dynamic_code_${path}`);
}
if (!sources["sidepanel.html"].includes('id="tab-save"') || !sources["sidepanel.html"].includes('id="tab-settings"')) failures.push("navigation");
if (/<script(?![^>]+src=)/i.test(sources["sidepanel.html"])) failures.push("inline_script");
if (!sources["src/service-worker.js"].includes("return true;")) failures.push("message_channel_compatibility");
if (!sources["src/service-worker.js"].includes('sender.url === chrome.runtime.getURL("sidepanel.html")')) failures.push("sender_identity");

const e2eSource = await readFile(new URL("scripts/extension-e2e.mjs", root), "utf8");
if (e2eSource.includes("...process.env")) failures.push("e2e_environment_inheritance");
if (!e2eSource.includes('PATH: process.env.PATH ?? ""')) failures.push("e2e_path_allowlist");

let recognized = 0;
for (const item of fixture.cases) {
  const actual = recognizePage(item.url);
  if (actual.supported !== item.supported || actual.platform !== item.platform || actual.executable !== false) {
    failures.push(`page_case_${item.id}`);
  } else {
    recognized += 1;
  }
}
if (new Set(fixture.cases.filter((item) => item.supported).map((item) => item.platform)).size !== 6) failures.push("six_platform_coverage");
if (SUPPORTED_PLATFORMS.length !== 6) failures.push("platform_registry");

if (failures.length > 0) {
  process.stderr.write(`${JSON.stringify({ code: "X2N_EXTENSION_INVALID", failures, status: "FAIL_CLOSED" })}\n`);
  process.exit(2);
}

process.stdout.write(
  `${JSON.stringify({
    action: "extension_self_test",
    extension_id: extensionId,
    fixture_cases: fixture.cases.length,
    fixture_recognition_passed: recognized,
    host_permissions: 0,
    permissions: expectedPermissions.length,
    platform_execution: "NOT_RUN",
    status: "PASS",
  })}\n`,
);
