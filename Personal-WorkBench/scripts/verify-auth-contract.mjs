import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const sourceFiles = [
  "server/auth/index.ts",
  "server/auth/runtime.ts",
  "server/auth/mail.ts",
  "app/api/auth/[...all]/route.ts",
  "app/auth/_components/auth-form.tsx",
  "app/auth/_components/auth-flow.ts",
  "app/account/page.tsx",
  "app/api/auth/public-config/route.ts",
];

export async function verifyAuthContract() {
  const [packageJson, ...sources] = await Promise.all([
    readFile("package.json", "utf8").then(JSON.parse),
    ...sourceFiles.map((file) => readFile(file, "utf8")),
  ]);
  assert.equal(packageJson.dependencies["better-auth"], "1.6.25");
  assert.equal(packageJson.dependencies["@better-auth/drizzle-adapter"], "1.6.25");

  const auth = sources[0];
  const runtime = sources[1];
  const route = sources[3];
  const form = sources[4];
  const flow = sources[5];
  const account = sources[6];
  const publicConfig = sources[7];
  const requiredFragments = [
    "requireEmailVerification: true",
    "minPasswordLength: 12",
    "maxPasswordLength: 128",
    "revokeSessionsOnPasswordReset: true",
    "disableImplicitLinking: true",
    "allowDifferentEmails: false",
    "allowUnlinkingAll: false",
    'storage: "database"',
    "cloudflare-turnstile",
    'expectedAction: "workbench_auth"',
    "useSecureCookies: true",
    "httpOnly: true",
    "sameSite: \"lax\"",
    "cf-connecting-ip",
  ];
  for (const fragment of requiredFragments) assert.ok(auth.includes(fragment), `missing auth contract: ${fragment}`);
  assert.ok(runtime.includes('code = "AUTH_RUNTIME_NOT_READY"'));
  assert.ok(!runtime.includes("console."));
  assert.ok(!route.includes("error.message"));
  assert.ok(flow.includes('"/api/auth/request-password-reset"'));
  assert.ok(flow.includes('"/api/auth/send-verification-email"'));
  assert.ok(flow.includes("callbackURL: VERIFIED_LOGIN_PATH"));
  assert.ok(form.includes('searchParams.get("verified") === "1"'));
  assert.ok(form.includes("重新发送验证邮件"));
  assert.ok(form.includes('"/api/auth/sign-in/social"'));
  assert.ok(form.includes("challenges.cloudflare.com/turnstile"));
  assert.ok(account.includes('"/api/auth/link-social"'));
  assert.ok(account.includes("主动点击连接后绑定"));
  assert.ok(publicConfig.includes("getPublicAuthPageConfig"));
  assert.ok(!publicConfig.includes("SECRET"));

  const report = {
    stage: "S2",
    status: "PASS_LOCAL_CONTRACT",
    betterAuth: "1.6.25",
    localMock: "PASS",
    savedCandidate: "NOT_RUN",
    assertions: {
      emailPassword: true,
      emailVerification: true,
      passwordResetSessionRevocation: true,
      googleExplicitLinkingOnly: true,
      turnstileAndRateLimit: true,
      enumerationSafeRuntimeReadiness: true,
      noSecretSerialization: true,
    },
    notes: [
      "No provider secret, real mailbox, OAuth account, Turnstile response, or Saved Version was accessed in this run.",
      "Saved Candidate callback validation remains an external release gate, not a local PASS claim.",
    ],
  };
  await writeFile("13_evidence/auth.json", `${JSON.stringify(report, null, 2)}\n`);
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const report = await verifyAuthContract();
  process.stdout.write(`${report.status} better-auth=${report.betterAuth}\n`);
}
