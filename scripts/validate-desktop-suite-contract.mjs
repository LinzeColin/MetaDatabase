#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const errors = [];

function absolute(relative) {
  return path.join(root, relative);
}

function fail(message) {
  errors.push(message);
}

function readJson(relative) {
  try {
    return JSON.parse(fs.readFileSync(absolute(relative), "utf8"));
  } catch (error) {
    fail(relative + ": " + error.message);
    return {};
  }
}

function readText(relative) {
  try {
    return fs.readFileSync(absolute(relative), "utf8");
  } catch (error) {
    fail(relative + ": " + error.message);
    return "";
  }
}

function requireValue(value, label) {
  if (typeof value !== "string" || value.length === 0) fail(label + " must be a non-empty string");
  return value;
}

function requirePath(relative) {
  if (!fs.existsSync(absolute(relative))) fail("required path is missing: " + relative);
}

const contract = readJson("desktop-suite/COMPATIBILITY_CONTRACT.json");
const modelContextPath = contract.sharedModelContext?.contract || "";
const modelContext = readJson(modelContextPath);
const release = contract.release || {};
const collaboration = contract.collaboration || {};
const applications = contract.applications && typeof contract.applications === "object" ? contract.applications : {};
const kimi = applications.kimiCode || {};
const harness = applications.harnessUI || {};
const dsh = applications.dshDesktop || {};

if (contract.schemaVersion !== 2) fail("schemaVersion must equal 2");
if (contract.repository?.canonical !== "LinzeColin/MetaDatabase") fail("repository.canonical must equal LinzeColin/MetaDatabase");
if (contract.repository?.branch !== "main") fail("repository.branch must equal main");
if (release.workflow !== ".github/workflows/desktop-app-suite-release.yml") fail("release.workflow must name the unified release workflow");
if (release.upstreamProposalWorkflow !== ".github/workflows/upstream-desktop-sync.yml") {
  fail("release.upstreamProposalWorkflow must name the upstream proposal workflow");
}
if (
  release.publishBranch !== "main" ||
  release.sourceCommit !== "GITHUB_SHA" ||
  release.releaseTargetMetadata !== "GITHUB_SHA" ||
  release.oneCommitForAllApps !== true ||
  release.exclusivePublisher !== true ||
  release.requireCurrentMain !== true ||
  release.provenanceAsset !== "Desktop.App.Suite-release.json"
) {
  fail("release must exclusively publish all three applications from the current main GITHUB_SHA");
}

if (collaboration.baseline !== "origin/main") fail("collaboration baseline must be origin/main");
if (collaboration.isolation !== "git-worktree") fail("collaboration isolation must be git-worktree");
if (collaboration.integration !== "pull-request") fail("collaboration integration must be pull-request");
if (collaboration.directMainPush !== false) fail("direct pushes to main must remain disabled by contract");
if (collaboration.requiredWorkflow !== ".github/workflows/kimi-harness-ci.yml") {
  fail("collaboration.requiredWorkflow must name the cross-platform CI workflow");
}
if (JSON.stringify(collaboration.applicationSet) !== JSON.stringify(["kimiCode", "harnessUI", "dshDesktop"])) {
  fail("collaboration.applicationSet must contain the three desktop applications in canonical order");
}

for (const [key, application] of Object.entries({ kimiCode: kimi, harnessUI: harness, dshDesktop: dsh })) {
  requireValue(application.name, "applications." + key + ".name");
  requireValue(application.bundleIdentifier, "applications." + key + ".bundleIdentifier");
  requireValue(application.releaseTagPrefix, "applications." + key + ".releaseTagPrefix");
  requireValue(application.upstream, "applications." + key + ".upstream");
  if (!Array.isArray(application.sourcePaths) || application.sourcePaths.length === 0) {
    fail("applications." + key + ".sourcePaths must list the maintained source paths");
  } else {
    application.sourcePaths.forEach(requirePath);
  }
}

if (kimi.bundleIdentifier !== "com.electron.kimi-code") fail("Kimi bundle identifier drifted");
if (harness.bundleIdentifier !== "com.linzecolin.harnessui") fail("Harness UI bundle identifier drifted");
if (dsh.bundleIdentifier !== "ai.deepseek.dsh.desktop") fail("DSH bundle identifier drifted");
if (kimi.upstream !== "MoonshotAI/kimi-code") fail("Kimi upstream drifted");
if (dsh.upstream !== "anywhere-labs/deepseek-harness-desktop") fail("DSH upstream drifted");
if (kimi.releaseTagPrefix !== "kimi-code-desktop-v") fail("Kimi release tag prefix drifted");
if (harness.releaseTagPrefix !== "harness-ui-v") fail("Harness UI release tag prefix drifted");
if (dsh.releaseTagPrefix !== "dsh-desktop-v") fail("DSH release tag prefix drifted");

const kimiPackage = readJson("Kimi-Code-Desktop/package.json");
const harnessPackage = readJson("Harness-UI/package.json");
if (kimi.versionSource !== "Kimi-Code-Desktop/package.json") fail("Kimi version source drifted");
if (harness.versionSource !== "Harness-UI/package.json") fail("Harness UI version source drifted");
requireValue(kimiPackage.version, "Kimi package version");
requireValue(harnessPackage.version, "Harness UI package version");
requireValue(dsh.version, "DSH version");

for (const relative of [
  "Kimi-Code-Desktop/src/runtime/harness.cjs",
  "Harness-UI/service/harness_service.py",
  "Harness-UI/dsh-plugin/lib/client.js",
  "Harness-UI/dsh-desktop/install-dsh-update.py",
  release.workflow || "",
  release.upstreamProposalWorkflow || "",
  collaboration.requiredWorkflow || "",
]) requirePath(relative);

const workflow = readText(release.workflow || "");
for (const required of [
  "node scripts/validate-desktop-suite-contract.mjs",
  "push:",
  "branches: [main]",
  "\"Kimi-Code-Desktop/**\"",
  "\"Harness-UI/**\"",
  "\"desktop-suite/**\"",
  "\"scripts/validate-desktop-suite-contract.mjs\"",
  "Desktop.App.Suite-release.json",
  "refs/heads/main",
  "applications.dshDesktop.version",
  "kimi_tag=kimi-code-desktop-v%s",
  "harness_tag=harness-ui-v%s",
  "dsh_tag=dsh-desktop-v%s",
  "release-assets/kimi 10",
  "release-assets/harness 8",
  "release-assets/dsh 4",
]) {
  if (!workflow.includes(required)) fail("unified release workflow must contain " + required);
}
if (!workflow.includes('git/ref/heads/main') || !workflow.includes('current_main="$')) {
  fail("unified release workflow must reject publication from a stale main commit");
}
if ((workflow.match(/target_commitish="\$GITHUB_SHA"/g) || []).length !== 1) {
  fail("unified release workflow must synchronize target_commitish through one shared publisher");
}
if ((workflow.match(/gh release create/g) || []).length !== 1 || (workflow.match(/gh release upload/g) || []).length !== 1) {
  fail("unified release workflow must have one shared publisher for all three applications");
}

const upstreamProposal = readText(release.upstreamProposalWorkflow || "");
for (const required of [
  "MoonshotAI/kimi-code",
  "anywhere-labs/deepseek-harness-desktop",
  "pull-requests: write",
  "git switch -c",
  "gh pr create",
  "gh workflow run kimi-harness-ci.yml",
]) {
  if (!upstreamProposal.includes(required)) fail("upstream proposal workflow must contain " + required);
}
if (/gh release (?:create|upload)|git\/refs\/tags|target_commitish|repos\/\$GITHUB_REPOSITORY\/releases/.test(upstreamProposal)) {
  fail("upstream proposal workflow must create a compatibility PR and must not publish releases or move tags");
}

for (const legacyWorkflow of [
  ".github/workflows/kimi-code-desktop-release.yml",
  ".github/workflows/harness-ui-release.yml",
]) {
  if (fs.existsSync(absolute(legacyWorkflow))) fail("legacy single-app publish workflow must be removed: " + legacyWorkflow);
}

const workflowsDirectory = absolute(".github/workflows");
const releaseWritePattern = /gh\s+release\s+(?:create|upload)|git\/refs\/tags|repos\/\$GITHUB_REPOSITORY\/releases/;
const desktopMarkerPattern = /kimi-code-desktop|harness-ui|dsh-desktop|Kimi Code Desktop|Harness UI|DSH Desktop/i;
for (const filename of fs.readdirSync(workflowsDirectory)) {
  if (!/\.ya?ml$/.test(filename)) continue;
  const relative = path.posix.join(".github/workflows", filename);
  if (relative === release.workflow) continue;
  const contents = readText(relative);
  if (releaseWritePattern.test(contents) && desktopMarkerPattern.test(contents)) {
    fail("desktop release publishing is exclusive to " + release.workflow + ": " + relative);
  }
}

const ciWorkflow = readText(collaboration.requiredWorkflow || "");
for (const required of [
  "name: Desktop suite contract",
  "node scripts/validate-desktop-suite-contract.mjs",
  "\"desktop-suite/**\"",
  "\"scripts/validate-desktop-suite-contract.mjs\"",
]) {
  if (!ciWorkflow.includes(required)) fail("cross-platform CI workflow must contain " + required);
}

const kimiHarnessCss = readText("Kimi-Code-Desktop/src/harness.css");
if (!kimiHarnessCss.includes('html[data-harness-ui="active"] #app .con')) {
  fail("Kimi populated-session surface must apply the shared main wash to #app .con");
}

const protocol = contract.sharedSkinProtocol || {};
if (protocol.owner !== "Harness UI") fail("Harness UI must remain the shared skin state owner");
if (protocol.serviceEndpoint !== "http://127.0.0.1:3099") fail("the shared skin service endpoint drifted");
if (protocol.serviceOwner !== "launch-agent-when-installed") fail("the installed LaunchAgent must own the shared skin service");
if (protocol.startupRecovery !== "continuous-retry-until-ready") fail("desktop clients must recover from startup ordering");
if (protocol.galleryRecovery !== "retry-while-visible") fail("the native gallery must recover while visible");
if (protocol.nextEndpoint !== "POST /api/next") fail("the shared next-skin action must remain POST /api/next");
if (protocol.shortcut !== "CmdOrCtrl+Shift+N") fail("the shared next-skin shortcut drifted");
if (!Array.isArray(contract.localOnly) || contract.localOnly.length === 0) fail("localOnly must document private runtime boundaries");

if (contract.sharedModelContext?.semantics !== "maximum-total-input-plus-output-tokens") {
  fail("sharedModelContext.semantics must describe the total model context window");
}
if (contract.sharedModelContext?.credentials !== "local-only") {
  fail("sharedModelContext credentials must remain local-only");
}
if (modelContext.schemaVersion !== 1) fail("model context contract schemaVersion must equal 1");
if (modelContext.contextWindowSemantics !== "maximum-total-input-plus-output-tokens") {
  fail("model context contract must use total-window semantics");
}

const routeByApplicationId = new Map();
for (const route of Array.isArray(modelContext.routes) ? modelContext.routes : []) {
  if (!Number.isSafeInteger(route.contextWindow) || route.contextWindow <= 0) {
    fail(`invalid context window for ${route.provider || "unknown"}/${route.upstreamModel || "unknown"}`);
    continue;
  }
  for (const [application, ids] of Object.entries(route.applications || {})) {
    if (!Array.isArray(ids) || ids.length === 0) {
      fail(`model context route ${route.provider}/${route.upstreamModel} has no ids for ${application}`);
      continue;
    }
    for (const id of ids) {
      const key = `${application}:${id}`;
      if (routeByApplicationId.has(key)) fail(`duplicate model context route: ${key}`);
      routeByApplicationId.set(key, route.contextWindow);
    }
  }
}

const requiredModelContexts = new Map([
  ["kimiCode:Kimi/k3", 1048576],
  ["dshDesktop:kimi-coding/k3", 1048576],
  ["kimiCode:Kimi/k3-256k", 262144],
  ["dshDesktop:kimi-coding/k3-256k", 262144],
  ["kimiCode:deepseek/deepseek-v4-flash", 1000000],
  ["dshDesktop:deepseek/deepseek-v4-flash", 1000000],
  ["kimiCode:deepseek/deepseek-v4-pro", 1000000],
  ["dshDesktop:deepseek/deepseek-v4-pro", 1000000],
  ["kimiCode:deepseek/deepseek-v4-flash-vision-exp", 1000000],
  ["dshDesktop:deepseek/deepseek-v4-flash-vision-exp", 1000000],
  ["kimiCode:scnet/DeepSeek-V4-Flash", 1000000],
  ["dshDesktop:scnet/DeepSeek-V4-Flash", 1000000],
  ["kimiCode:scnet/DeepSeek-V4-Pro", 1000000],
  ["dshDesktop:scnet/DeepSeek-V4-Pro", 1000000],
  ["kimiCode:scnet/Kimi-K3", 1048576],
  ["dshDesktop:scnet/Kimi-K3", 1048576],
  ["kimiCode:scnet/Qwen3.8-Max", 1000000],
  ["dshDesktop:scnet/Qwen3.8-Max", 1000000],
  ["kimiCode:scnet/MiniMax-M3", 1000000],
  ["dshDesktop:scnet/MiniMax-M3", 1000000],
  ["kimiCode:scnet/GLM-5.2", 1000000],
  ["dshDesktop:scnet/GLM-5.2", 1000000],
]);
for (const [key, expected] of requiredModelContexts) {
  if (routeByApplicationId.get(key) !== expected) fail(`${key} context window must equal ${expected}`);
}

const aliases = Array.isArray(modelContext.compatibilityAliases) ? modelContext.compatibilityAliases : [];
for (const expected of ["scnet/deepseek-v4-flash-0731", "scnet/glm-5.2"]) {
  const alias = aliases.find((entry) => entry.application === "kimiCode" && entry.alias === expected);
  if (alias?.deletionRule !== "retain-while-session-references-exist") {
    fail(`compatibility alias ${expected} must remain until session references are gone`);
  }
  if (!routeByApplicationId.has(`kimiCode:${alias?.canonical || ""}`)) {
    fail(`compatibility alias ${expected} must point to a canonical Kimi model route`);
  }
}

if (errors.length) {
  console.error("Desktop suite compatibility contract is invalid:");
  for (const error of errors) console.error("- " + error);
  process.exitCode = 1;
} else {
  console.log("Desktop suite contract valid: Kimi " + kimiPackage.version + ", Harness UI " + harnessPackage.version + ", DSH " + dsh.version + ".");
}
