import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("macOS opens the complete library in an in-app WebKit window", () => {
  const delegate = fs.readFileSync(path.join(projectRoot, "macos/Sources/HarnessUIApp/AppDelegate.swift"), "utf8");
  const gallery = fs.readFileSync(path.join(projectRoot, "macos/Sources/HarnessUIApp/GalleryWindowController.swift"), "utf8");
  const plist = fs.readFileSync(path.join(projectRoot, "macos/Info.plist"), "utf8");
  const kimi = fs.readFileSync(path.join(projectRoot, "../Kimi-Code-Desktop/src/main.cjs"), "utf8");
  assert.match(delegate, /打开完整素材库/);
  assert.match(delegate, /GalleryWindowController\(port: configuration\.port\)/);
  assert.doesNotMatch(delegate, /NSWorkspace\.shared\.open\(URL\(string: "http:\/\/127\.0\.0\.1/);
  assert.match(gallery, /import WebKit/);
  assert.match(gallery, /WKWebView/);
  assert.match(gallery, /makeKeyAndOrderFront/);
  assert.match(delegate, /applicationShouldHandleReopen/);
  assert.match(delegate, /open urls: \[URL\]/);
  assert.match(plist, /<string>harnessui<\/string>/);
  assert.match(kimi, /process\.platform === "darwin" \? "harnessui:\/\/library"/);
});

test("Kimi and DSH wait for the shared SMB deployment result", () => {
  const kimiBridge = fs.readFileSync(path.join(projectRoot, "../Kimi-Code-Desktop/src/runtime/harness.cjs"), "utf8");
  const dsh = fs.readFileSync(path.join(projectRoot, "dsh-plugin/lib/client.js"), "utf8");
  for (const source of [kimiBridge, dsh]) {
    assert.match(source, /refresh-status\.json/);
    assert.match(source, /\["ready", "partial"\]/);
    assert.match(source, /素材目录仍在扫描/);
  }
});
