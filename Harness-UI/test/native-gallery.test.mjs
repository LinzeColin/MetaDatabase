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
  assert.match(gallery, /override func performKeyEquivalent/);
  assert.match(gallery, /case "r":/);
  assert.match(gallery, /case "w":/);
  assert.match(gallery, /case "q":/);
  assert.match(delegate, /applicationShouldHandleReopen/);
  assert.match(delegate, /open urls: \[URL\]/);
  assert.match(plist, /<string>harnessui<\/string>/);
  assert.match(plist, /NSNetworkVolumesUsageDescription/);
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

test("the GUI-owned helper performs SMB deployment for the background service", () => {
  const delegate = fs.readFileSync(path.join(projectRoot, "macos/Sources/HarnessUIApp/AppDelegate.swift"), "utf8");
  const catalogBuilder = fs.readFileSync(path.join(projectRoot, "macos/Sources/HarnessUICore/CatalogBuilder.swift"), "utf8");
  const service = fs.readFileSync(path.join(projectRoot, "service/harness_service.py"), "utf8");
  assert.match(delegate, /\/api\/source-sync/);
  assert.match(delegate, /syncHelperPort/);
  assert.match(catalogBuilder, /synchronizeSourceToMaster/);
  assert.match(catalogBuilder, /buildLocalCatalog/);
  assert.match(service, /native_source_sync/);
  assert.match(service, /sourceOwner/);
});

test("the in-app gallery refreshes SMB status even when skin state is unchanged", () => {
  const source = fs.readFileSync(path.join(projectRoot, "web/app.js"), "utf8");
  assert.match(source, /Promise\.all\(\[json\("\/state\.json"\), json\("\/refresh-status\.json"\)\]\)/);
  assert.match(source, /refreshChanged/);
  assert.match(source, /refreshStatus = latestRefreshStatus/);
});

test("the macOS app and installer wait for the configured shared service", () => {
  const delegate = fs.readFileSync(path.join(projectRoot, "macos/Sources/HarnessUIApp/AppDelegate.swift"), "utf8");
  const installer = fs.readFileSync(path.join(projectRoot, "service/install-macos.sh"), "utf8");
  assert.match(delegate, /sharedServiceLaunchAgent/);
  assert.match(delegate, /attempts = configured \? 12 : 1/);
  assert.match(delegate, /Thread\.sleep\(forTimeInterval: 0\.5\)/);
  assert.match(installer, /http:\/\/127\.0\.0\.1:3099\/state\.json/);
  assert.match(installer, /harness_service_ready/);
  assert.match(installer, /launchctl enable "gui\/\$uid\/com\.harnessui\.smb"/);
  assert.match(installer, /launchctl enable "gui\/\$uid\/com\.harnessui\.assets"/);
});

test("the SMB mount agent tolerates a TCC-restricted marker only after exact share verification", () => {
  const mountScript = fs.readFileSync(path.join(projectRoot, "service/mount-harness-smb.sh"), "utf8");
  assert.match(mountScript, /smbutil statshares/);
  assert.match(mountScript, /"SERVER_NAME" : "192\.168\.0\.1"/);
  assert.match(mountScript, /"share_name" : "share"/);
  assert.match(mountScript, /\[ -e "\$volume_id_file" \] \|\| return 1/);
  assert.match(mountScript, /if detected_volume_id=.*sed -n '1p'.*2>\/dev\/null/);
  assert.match(mountScript, /\[ "\$detected_volume_id" = "\$volume_id" \] \|\| return 1/);
});
