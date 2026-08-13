import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("retired-domain redirect carries only a bounded anonymous history payload beside the opaque session handoff", async () => {
  const [redirect, contract, recovery, completion, nextConfig, authPages, authHandoff, account, home] = await Promise.all([
    readFile("app/_components/workbench/legacy-domain-redirect.tsx", "utf8"),
    readFile("app/_components/workbench/legacy-domain-handoff.ts", "utf8"),
    readFile("app/_components/workbench/legacy-domain-history-recovery.tsx", "utf8"),
    readFile("app/api/auth/legacy-domain-handoff/complete/route.ts", "utf8"),
    readFile("next.config.ts", "utf8"),
    Promise.all([
      "sign-in",
      "sign-up",
      "forgot-password",
      "reset-password",
      "verify-email",
    ].map((route) => readFile(`app/auth/${route}/page.tsx`, "utf8"))),
    readFile("app/auth/_components/legacy-auth-handoff.tsx", "utf8"),
    readFile("app/account/page.tsx", "utf8"),
    readFile("app/page.tsx", "utf8"),
  ]);

  assert.match(redirect, /fetch\("\/api\/auth\/legacy-domain-handoff", \{/);
  assert.match(redirect, /credentials: "same-origin"/);
  assert.match(redirect, /form\.method = "POST"/);
  assert.match(redirect, /buildGuestDeviceHistoryEnvelope/);
  assert.match(redirect, /serializeLegacyDeviceHistoryPayload/);
  assert.match(redirect, /appendHiddenValue\(form, "history", history\)/);
  assert.match(redirect, /window\.location\.replace\(destination\)/);
  assert.doesNotMatch(redirect, /document\.cookie|localStorage|sessionStorage\./);
  assert.match(recovery, /restoreLegacyGuestDeviceHistory/);
  assert.match(recovery, /LEGACY_DEVICE_HISTORY_SESSION_KEY/);
  assert.match(completion, /serializeLegacyDeviceHistoryPayload/);
  assert.match(completion, /sessionStorage\.setItem/);
  assert.doesNotMatch(completion, /legacy-import\/apply|legacy-import\/preview/);
  assert.match(contract, /safeAccountReturnPath/);
  assert.match(contract, /HANDOFF_ID_PATTERN/);
  assert.match(nextConfig, /allowedDevOrigins: \[RETIRED_WORKBENCH_HOST\]/);
  assert.match(nextConfig, /allowedOrigins: \[RETIRED_WORKBENCH_HOST\]/);
  assert.match(nextConfig, /bodySizeLimit: "8mb"/);
  for (const page of authPages) {
    assert.match(page, /isRetiredAuthHost\(\)/);
    assert.match(page, /LegacyAuthHandoff/);
  }
  assert.match(authHandoff, /LegacyDomainRedirect/);
  assert.doesNotMatch(authHandoff, /sign-in\/social|AuthForm/);
  assert.match(account, /LegacyDomainRedirect/);
  assert.match(redirect, /initiallyRetiredHost/);
  assert.match(redirect, /legacy-domain-transfer/);
  assert.match(home, /isRetiredCompatibilityHost/);
  assert.match(home, /initiallyRetiredHost=\{retiredHost\}/);
});
