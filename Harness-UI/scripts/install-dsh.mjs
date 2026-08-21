import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptRoot, "..");
const source = path.join(projectRoot, "dsh-plugin");

function argument(name) {
  const prefix = `--${name}=`;
  const inline = process.argv.slice(2).find((value) => value.startsWith(prefix));
  if (inline) return inline.slice(prefix.length);
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 ? process.argv[index + 1] : null;
}

const apply = process.argv.includes("--apply");
const dshRoot = path.resolve(argument("dsh-root") || path.join(os.homedir(), ".dsh"));
const profileRoot = path.join(dshRoot, "profiles", "desktop");
const packageFile = path.join(profileRoot, "package.json");
const pluginTarget = path.join(dshRoot, "plugins", "dsh-harness-ui-skins");
const moduleTarget = path.join(profileRoot, "node_modules", "dsh-harness-ui-skins");

if (!fs.existsSync(packageFile)) throw new Error(`DSH desktop profile not found: ${packageFile}`);
const profile = JSON.parse(fs.readFileSync(packageFile, "utf8"));
const linkPath = pluginTarget.replaceAll(path.sep, "/");
profile.dependencies ||= {};
profile.dependencies["dsh-harness-ui-skins"] = `link:${linkPath}`;
profile.dsh ||= {};
profile.dsh.profile ||= {};
profile.dsh.profile.bundles ||= [];
if (!profile.dsh.profile.bundles.includes("dsh-harness-ui-skins"))
  profile.dsh.profile.bundles.push("dsh-harness-ui-skins");

console.log(`DSH root: ${dshRoot}`);
console.log(`Plugin:   ${pluginTarget}`);
console.log(`Profile:  ${packageFile}`);
if (!apply) {
  console.log("Preview only. Re-run with --apply to install; DSH will not be restarted.");
  process.exit(0);
}

const stamp = new Date().toISOString().replaceAll(/[:.]/g, "-");
const backupRoot = path.join(dshRoot, "_harness-ui-backups", stamp);
fs.mkdirSync(backupRoot, { recursive: true });

function moveAside(target, name) {
  try {
    fs.lstatSync(target);
    fs.renameSync(target, path.join(backupRoot, name));
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
}

moveAside(pluginTarget, "plugin");
moveAside(moduleTarget, "profile-module");
fs.copyFileSync(packageFile, path.join(backupRoot, "profile-package.json"));

fs.mkdirSync(path.dirname(pluginTarget), { recursive: true });
fs.cpSync(source, pluginTarget, { recursive: true });
fs.mkdirSync(path.dirname(moduleTarget), { recursive: true });
fs.cpSync(source, moduleTarget, { recursive: true });

const temporary = `${packageFile}.harness-ui.tmp`;
fs.writeFileSync(temporary, `${JSON.stringify(profile, null, 2)}\n`);
fs.renameSync(temporary, packageFile);

console.log(`Installed dsh-harness-ui-skins 1.0.0. Backup: ${backupRoot}`);
console.log("DSH was not restarted. Fully quit and reopen DSH when you are ready to activate the plugin.");
