import { spawn } from "node:child_process";
import process from "node:process";

const migrate = spawn(process.execPath, ["scripts/vps3/migrate-runtime.mjs"], {
  stdio: "inherit",
  env: process.env,
});
const migrationExit = await new Promise((resolve) => migrate.once("exit", resolve));
if (migrationExit !== 0) process.exit(Number(migrationExit ?? 1));

const server = spawn(process.execPath, ["server.js"], {
  stdio: "inherit",
  env: process.env,
});
for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => server.kill(signal));
}
server.once("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(Number(code ?? 0));
});
