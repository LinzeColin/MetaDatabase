import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { recognizePage, SUPPORTED_PLATFORMS } from "../src/page-support.js";
import { buildBilibiliCapturePayload, validateBilibiliPageFacts } from "../src/bilibili-current-page.js";
import { buildDouyinCapturePayload, validateDouyinPageFacts } from "../src/douyin-current-page.js";
import { DouyinShortLinkError, resolveDouyinShortLink } from "../src/douyin-short-link.js";
import { buildXhsCapturePayload, validateXhsPageFacts } from "../src/xhs-current-page.js";

const root = new URL("../", import.meta.url);
const manifest = JSON.parse(await readFile(new URL("manifest.json", root), "utf8"));
const fixture = JSON.parse(
  await readFile(new URL("../../packages/test-fixtures/extension/v1/page_cases.json", root), "utf8"),
);
const xhsFixture = JSON.parse(
  await readFile(
    new URL("../../packages/test-fixtures/extension/v1/xhs_current_page/fixture_manifest.json", root),
    "utf8",
  ),
);
const douyinFixture = JSON.parse(
  await readFile(
    new URL("../../packages/test-fixtures/extension/v1/douyin_current_page/fixture_manifest.json", root),
    "utf8",
  ),
);
const bilibiliFixture = JSON.parse(
  await readFile(
    new URL("../../packages/test-fixtures/extension/v1/bilibili_current_page/fixture_manifest.json", root),
    "utf8",
  ),
);
const sourceFiles = [
  "sidepanel.html",
  "src/bilibili-current-page.js",
  "src/douyin-current-page.js",
  "src/douyin-short-link.js",
  "src/page-support.js",
  "src/service-worker.js",
  "src/sidepanel.js",
  "src/xhs-current-page.js",
  "styles/sidepanel.css",
];
const sources = Object.fromEntries(
  await Promise.all(sourceFiles.map(async (path) => [path, await readFile(new URL(path, root), "utf8")])),
);

const failures = [];
const expectedPermissions = ["activeTab", "nativeMessaging", "scripting", "sidePanel"];
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

const forbiddenManifestValues = ["<all_urls>", "cookies", "storage", "tabs"];
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
  const expectedExecutable = item.supported && item.platform === "xiaohongshu";
  if (actual.supported !== item.supported || actual.platform !== item.platform || actual.executable !== expectedExecutable) {
    failures.push(`page_case_${item.id}`);
  } else {
    recognized += 1;
  }
}
if (new Set(fixture.cases.filter((item) => item.supported).map((item) => item.platform)).size !== 6) failures.push("six_platform_coverage");
if (SUPPORTED_PLATFORMS.length !== 6) failures.push("platform_registry");
if (recognizePage("https://www.xiaohongshu.com/explore/64f000000000000000000001").executable) {
  failures.push("xhs_real_page_gate");
}
if (recognizePage("https://www.douyin.com/video/7485211130848218428").executable) {
  failures.push("douyin_real_page_gate");
}
if (recognizePage("https://v.douyin.com/opaque-real-shaped/").supported) {
  failures.push("douyin_real_short_link_gate");
}
if (recognizePage("https://www.douyin.com/note/7485211130848218428").supported) {
  failures.push("douyin_unknown_gallery_route_gate");
}
for (const url of [
  "https://www.bilibili.com/video/BV1RealShape0",
  "https://www.bilibili.com/read/cv100000001",
]) {
  const support = recognizePage(url);
  if (!support.supported || support.executable || support.platform !== "bilibili") {
    failures.push("bilibili_real_page_gate");
  }
}
for (const url of [
  "https://www.bilibili.com/video/synthetic-bili-video-self-test",
  "https://www.bilibili.com/read/synthetic-bili-article-self-test",
]) {
  const support = recognizePage(url);
  if (!support.supported || !support.executable || support.platform !== "bilibili") {
    failures.push("bilibili_synthetic_page_gate");
  }
}
if (recognizePage("https://bilibili.com/read/synthetic-bili-article-self-test").executable) {
  failures.push("bilibili_noncanonical_host_gate");
}
if (recognizePage("https://www.bilibili.com/video/synthetic-bili-video-self-test?p=2").executable) {
  failures.push("bilibili_semantic_query_gate");
}
for (const url of [
  "https://www.douyin.com/video/synthetic-video-self-test",
  "https://www.douyin.com/note/synthetic-gallery-self-test",
  "https://v.douyin.com/synthetic-short-self-test/",
]) {
  const support = recognizePage(url);
  if (!support.supported || !support.executable || support.platform !== "douyin") {
    failures.push("douyin_synthetic_page_gate");
  }
}

if (xhsFixture.synthetic !== true || xhsFixture.cases.length !== 5) failures.push("xhs_fixture_manifest");
for (const field of [
  "contains_credentials",
  "contains_local_absolute_paths",
  "contains_media_urls",
  "contains_private_content",
  "contains_real_accounts",
  "real_accounts",
]) {
  if (xhsFixture[field] !== false) failures.push(`xhs_fixture_${field}`);
  if (douyinFixture[field] !== false) failures.push(`douyin_fixture_${field}`);
  if (bilibiliFixture[field] !== false) failures.push(`bilibili_fixture_${field}`);
}
if (
  bilibiliFixture.synthetic !== true
  || bilibiliFixture.cases.length !== 10
  || bilibiliFixture.policy_cases.length !== 8
) failures.push("bilibili_fixture_manifest");
if (douyinFixture.synthetic !== true || douyinFixture.cases.length !== 8) failures.push("douyin_fixture_manifest");
if (!Array.isArray(douyinFixture.short_link_cases) || douyinFixture.short_link_cases.length !== 16) {
  failures.push("douyin_short_link_fixture_manifest");
}
const contractFact = validateXhsPageFacts({
  page_context: {
    content_id: "synthetic-note-contract-001",
    content_type: "unknown",
    title: null,
  },
  page_url: "https://www.xiaohongshu.com/explore/synthetic-note-contract-001",
  platform: "xiaohongshu",
  provenance: {
    canonical_url: { source: "stable_content_id", status: "derived" },
    content_id: { source: "location_path_and_detail_surface", status: "observed_verified" },
    content_type: { source: null, status: "unknown" },
    title: { source: null, status: "missing" },
  },
  schema_version: "1.0",
  status: "ready",
});
const contractPayload = buildXhsCapturePayload(contractFact);
if (new URL(contractPayload.page_url).search || new URL(contractPayload.page_url).hash) failures.push("xhs_canonical_url");
try {
  buildXhsCapturePayload(validateXhsPageFacts({
    code: "X2N_PLATFORM_CHANGED",
    platform: "xiaohongshu",
    reason: "detail_surface_missing",
    schema_version: "1.0",
    status: "platform_changed",
  }));
  failures.push("xhs_platform_changed_capture");
} catch {
  // Expected fail-closed path.
}

const bilibiliContractFact = validateBilibiliPageFacts({
  page_context: {
    content_id: "synthetic-bili-article-contract-001",
    content_type: "text",
    title: null,
  },
  page_url: "https://www.bilibili.com/read/synthetic-bili-article-contract-001",
  platform: "bilibili",
  provenance: {
    canonical_url: { source: "stable_content_id_and_page_kind", status: "derived" },
    content_id: { source: "location_path_and_detail_surface", status: "observed_verified" },
    content_type: { source: "detail_text_marker", status: "observed" },
    title: { source: null, status: "missing" },
  },
  schema_version: "1.0",
  status: "ready",
});
const bilibiliContractPayload = buildBilibiliCapturePayload(bilibiliContractFact);
if (new URL(bilibiliContractPayload.page_url).search || new URL(bilibiliContractPayload.page_url).hash) {
  failures.push("bilibili_canonical_url");
}
try {
  buildBilibiliCapturePayload(validateBilibiliPageFacts({
    code: "X2N_PLATFORM_CHANGED",
    platform: "bilibili",
    reason: "detail_surface_missing",
    schema_version: "1.0",
    status: "platform_changed",
  }));
  failures.push("bilibili_platform_changed_capture");
} catch {
  // Expected fail-closed path.
}

const douyinContractFact = validateDouyinPageFacts({
  page_context: {
    content_id: "synthetic-video-contract-001",
    content_type: "unknown",
    title: null,
  },
  page_url: "https://www.douyin.com/video/synthetic-video-contract-001",
  platform: "douyin",
  provenance: {
    canonical_url: { source: "stable_content_id_and_kind", status: "derived" },
    content_id: { source: "location_path_and_detail_surface", status: "observed_verified" },
    content_type: { source: null, status: "unknown" },
    title: { source: null, status: "missing" },
  },
  schema_version: "1.0",
  status: "ready",
});
const douyinContractPayload = buildDouyinCapturePayload(douyinContractFact);
if (new URL(douyinContractPayload.page_url).search || new URL(douyinContractPayload.page_url).hash) {
  failures.push("douyin_canonical_url");
}
try {
  buildDouyinCapturePayload(validateDouyinPageFacts({
    code: "X2N_PLATFORM_CHANGED",
    platform: "douyin",
    reason: "detail_surface_missing",
    schema_version: "1.0",
    status: "platform_changed",
  }));
  failures.push("douyin_platform_changed_capture");
} catch {
  // Expected fail-closed path.
}

const shortRequestOptions = [];
const shortResolved = await resolveDouyinShortLink(
  "https://v.douyin.com/synthetic-self-test/",
  async (request) => {
    shortRequestOptions.push(request);
    return {
      location: "https://www.douyin.com/video/synthetic-resolved-self-test?tracking=discarded",
      status: 302,
    };
  },
);
if (
  shortResolved.page_url !== "https://www.douyin.com/video/synthetic-resolved-self-test"
  || shortResolved.redirect_count !== 1
  || shortRequestOptions.length !== 1
  || shortRequestOptions[0].credentials !== "omit"
  || shortRequestOptions[0].redirect !== "manual"
) failures.push("douyin_short_link_resolution");
try {
  await resolveDouyinShortLink(
    "https://v.douyin.com/synthetic-self-test-blocked/",
    async () => ({ location: "https://127.0.0.1/private", status: 302 }),
  );
  failures.push("douyin_short_link_ssrf");
} catch (error) {
  if (!(error instanceof DouyinShortLinkError) || error.code !== "X2N_SHORTLINK_HOST_BLOCKED") {
    failures.push("douyin_short_link_ssrf_error");
  }
}

if (failures.length > 0) {
  process.stderr.write(`${JSON.stringify({ code: "X2N_EXTENSION_INVALID", failures, status: "FAIL_CLOSED" })}\n`);
  process.exit(2);
}

process.stdout.write(
  `${JSON.stringify({
    action: "extension_self_test",
    bilibili_fixture_cases: bilibiliFixture.cases.length,
    bilibili_policy_cases: bilibiliFixture.policy_cases.length,
    douyin_fixture_cases: douyinFixture.cases.length,
    douyin_shortlink_cases: douyinFixture.short_link_cases.length,
    extension_id: extensionId,
    fixture_cases: fixture.cases.length,
    fixture_recognition_passed: recognized,
    host_permissions: 0,
    permissions: expectedPermissions.length,
    platform_execution: "NOT_RUN",
    status: "PASS",
    xhs_fixture_cases: xhsFixture.cases.length,
  })}\n`,
);
