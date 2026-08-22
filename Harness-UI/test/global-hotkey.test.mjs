import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("macOS registers Command-Shift-N as a process-wide next-skin shortcut", () => {
  const hotKey = fs.readFileSync(path.join(projectRoot, "macos/Sources/HarnessUIApp/GlobalHotKey.swift"), "utf8");
  const delegate = fs.readFileSync(path.join(projectRoot, "macos/Sources/HarnessUIApp/AppDelegate.swift"), "utf8");
  assert.match(hotKey, /RegisterEventHotKey/);
  assert.match(hotKey, /kVK_ANSI_N/);
  assert.match(hotKey, /cmdKey \| shiftKey/);
  assert.match(delegate, /nextSkinHotKey = try \.commandShiftN/);
  assert.match(delegate, /self\?\.nextSkin\(\)/);
});
