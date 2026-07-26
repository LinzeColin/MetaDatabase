const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const APP_ROOT = path.resolve(__dirname, "..");

test("active App surfaces do not clone, sync, or route users to historical upstream", () => {
  const activeFiles = [
    "README.md",
    "README.en.md",
    "README.zh-CN.md",
    "package.json",
    "package-lock.json",
    "src/core/app.js",
  ];
  const forbidden = [
    /WenXiaoWendy/,
    /github\.com\/[^/\s]+\/(?:cyberboss|timeline-for-agent|whereabouts-mcp)/i,
    /git(?:\+https)?:\/\/[^"' \n]+(?:cyberboss|timeline-for-agent|whereabouts-mcp)/i,
  ];
  for (const relative of activeFiles) {
    const source = fs.readFileSync(path.join(APP_ROOT, relative), "utf8");
    for (const pattern of forbidden) {
      assert.doesNotMatch(source, pattern, `${relative} contains ${pattern}`);
    }
  }
});

test("App dependencies use local fixed vendor bundles instead of Git branches", () => {
  const packageJson = JSON.parse(
    fs.readFileSync(path.join(APP_ROOT, "package.json"), "utf8")
  );
  assert.equal(
    packageJson.dependencies["timeline-for-agent"],
    "file:../vendor/timeline-for-agent"
  );
  assert.equal(
    packageJson.dependencies["whereabouts-mcp"],
    "file:../vendor/whereabouts-mcp"
  );
  const lock = fs.readFileSync(path.join(APP_ROOT, "package-lock.json"), "utf8");
  assert.doesNotMatch(lock, /git\+|github:|#(?:main|master)\b/i);
});
