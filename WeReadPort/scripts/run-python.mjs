import { spawnSync } from "node:child_process";
import { resolvePythonCommand } from "./python-runtime.mjs";

const args = process.argv.slice(2);
if (!args.length) throw new Error("需要传入 Python 命令参数。");
const result = spawnSync(resolvePythonCommand(), args, { stdio: "inherit", env: process.env });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
