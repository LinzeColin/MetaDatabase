import { mkdir, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const reportPath = resolve(process.env.RESILIENCE_EVIDENCE_FILE || join(ROOT, "13_evidence", "resilience.json"));
const testCmd = process.execPath;

async function run(cmdArgs: string[]) {
  const child = spawn(testCmd, cmdArgs, {
    cwd: ROOT,
    stdio: "ignore",
  });

  const status = await new Promise<number>((resolve) => {
    child.on("close", (code) => resolve(code ?? 1));
  });

  return { status };
}

(async () => {
  const checks = {
    test_target: "tests/outbox-replay.test.mts",
    runtime: "node-test",
    output_captured: false,
  };

  const result = await run([ "--experimental-strip-types", "--test", "tests/outbox-replay.test.mts" ]);

  const evidence = {
    schema_version: "2.0",
    stage: "S4",
    phase: "S4-T2",
    status: result.status === 0 ? "PASS_LOCAL_RETRY_RESILIENCE" : "FAIL_LOCAL_RETRY_RESILIENCE",
    runAt: new Date().toISOString(),
    checks,
    test: {
      statusCode: result.status,
      output_captured: false,
      output_redacted: true,
    },
    notes: [
      "离线队列重放行为采用可测纯函数，支持冲突/不可用/网络异常下停止重放并保留未成功记录。",
      "在 503 与网络异常下，未发送成功的动作不会丢弃；顺序可追踪。",
    ],
  };

  await mkdir(dirname(reportPath), { recursive: true });
  await writeFile(reportPath, `${JSON.stringify(evidence, null, 2)}\n`);

  if (result.status !== 0) {
    throw new Error(`verify-offline-replay tests failed with code ${result.status}`);
  }

  console.log(evidence.status, "test_status=", result.status);
})().catch((error) => {
  process.exitCode = 1;
  console.error(error);
});
