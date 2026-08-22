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

const contractPath = "desktop-suite/COMPATIBILITY_CONTRACT.json";
const contract = readJson(contractPath);
const applications = contract.applications && typeof contract.applications === "object" ? contract.applications : {};
const kimi = applications.kimiCode || {};
const harness = applications.harnessUI || {};
const dsh = applications.dshDesktop || {};

if (contract.schemaVersion !== 1) fail("schemaVersion must equal 1");
if (contract.repository?.canonical !== "LinzeColin/MetaDatabase") fail("repository.canonical must equal LinzeColin/MetaDatabase");
if (contract.repository?.branch !== "main") fail("repository.branch must equal main");
if (contract.release?.workflow !== ".github/workflows/desktop-app-suite-release.yml") fail("release.workflow must name the unified release workflow");
if (contract.release?.sourceCommit !== "GITHUB_SHA" || contract.release?.oneCommitForAllApps !== true) {
  fail("release must publish all three applications from GITHUB_SHA");
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
  contract.release?.workflow || "",
]) requirePath(relative);

const workflow = readText(contract.release?.workflow || "");
for (const required of [
  "node scripts/validate-desktop-suite-contract.mjs",
  "\"Kimi-Code-Desktop/**\"",
  "\"Harness-UI/**\"",
  "\"desktop-suite/**\"",
  "\"scripts/validate-desktop-suite-contract.mjs\"",
  "kimi_tag=kimi-code-desktop-v%s",
  "harness_tag=harness-ui-v%s",
  "dsh_tag=dsh-desktop-v%s",
]) {
  if (!workflow.includes(required)) fail("unified release workflow must contain " + required);
}
const dshDefault = 'dsh_version="' + "$" + "{INPUT_DSH_VERSION:-" + dsh.version + '}"';
if (!workflow.includes('default: "' + dsh.version + '"') || !workflow.includes(dshDefault)) {
  fail("unified release workflow must use the contract DSH version");
}
if ((workflow.match(/\$GITHUB_SHA/g) || []).length < 3) {
  fail("unified release workflow must target GITHUB_SHA for every application release");
}

const protocol = contract.sharedSkinProtocol || {};
if (protocol.owner !== "Harness UI") fail("Harness UI must remain the shared skin state owner");
if (protocol.nextEndpoint !== "POST /api/next") fail("the shared next-skin action must remain POST /api/next");
if (protocol.shortcut !== "CmdOrCtrl+Shift+N") fail("the shared next-skin shortcut drifted");
if (!Array.isArray(contract.localOnly) || contract.localOnly.length === 0) fail("localOnly must document private runtime boundaries");

if (errors.length) {
  console.error("Desktop suite compatibility contract is invalid:");
  for (const error of errors) console.error("- " + error);
  process.exitCode = 1;
} else {
  console.log("Desktop suite contract valid: Kimi " + kimiPackage.version + ", Harness UI " + harnessPackage.version + ", DSH " + dsh.version + ".");
}
