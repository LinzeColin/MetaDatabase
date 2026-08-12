import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("retired-domain redirect uses an opaque POST handoff and retains a safe fallback", async () => {
  const [redirect, contract] = await Promise.all([
    readFile("app/_components/workbench/legacy-domain-redirect.tsx", "utf8"),
    readFile("app/_components/workbench/legacy-domain-handoff.ts", "utf8"),
  ]);

  assert.match(redirect, /fetch\("\/api\/auth\/legacy-domain-handoff", \{/);
  assert.match(redirect, /credentials: "same-origin"/);
  assert.match(redirect, /form\.method = "POST"/);
  assert.match(redirect, /window\.location\.replace\(destination\)/);
  assert.doesNotMatch(redirect, /document\.cookie|localStorage|sessionStorage/);
  assert.match(contract, /safeAccountReturnPath/);
  assert.match(contract, /HANDOFF_ID_PATTERN/);
});
