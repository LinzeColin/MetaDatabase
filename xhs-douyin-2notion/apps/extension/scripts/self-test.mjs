import { readFile } from "node:fs/promises";

const manifest = JSON.parse(
  await readFile(new URL("../manifest.json", import.meta.url), "utf8"),
);

const failures = [];
if (manifest.manifest_version !== 3) failures.push("manifest_version");
if (manifest.version !== "0.0.0.1") failures.push("version");
if (!Array.isArray(manifest.permissions) || manifest.permissions.length !== 0) {
  failures.push("permissions");
}
if (Object.hasOwn(manifest, "host_permissions")) failures.push("host_permissions");
if (Object.hasOwn(manifest, "background")) failures.push("background");
if (Object.hasOwn(manifest, "side_panel")) failures.push("side_panel");

if (failures.length > 0) {
  process.stderr.write(
    `${JSON.stringify({ code: "X2N_SCAFFOLD_EXTENSION_INVALID", failures, status: "FAIL_CLOSED" })}\n`,
  );
  process.exit(2);
}

process.stdout.write(
  `${JSON.stringify({ action: "extension_self_test", permissions: 0, status: "PASS" })}\n`,
);
