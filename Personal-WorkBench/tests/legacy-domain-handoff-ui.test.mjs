import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("retired-domain redirect carries only a bounded anonymous history payload beside the opaque session handoff", async () => {
  const [redirect, contract, recovery, completion] = await Promise.all([
    readFile("app/_components/workbench/legacy-domain-redirect.tsx", "utf8"),
    readFile("app/_components/workbench/legacy-domain-handoff.ts", "utf8"),
    readFile("app/_components/workbench/legacy-domain-history-recovery.tsx", "utf8"),
    readFile("app/api/auth/legacy-domain-handoff/complete/route.ts", "utf8"),
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
});
