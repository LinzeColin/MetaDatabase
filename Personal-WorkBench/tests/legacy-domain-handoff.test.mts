import assert from "node:assert/strict";
import test from "node:test";
import {
  LEGACY_DOMAIN_HANDOFF_TTL_MS,
  canonicalHandoffDestination,
  consumeLegacyDomainHandoff,
  isCanonicalHandoffCompletionRequest,
  isRetiredHandoffIssuanceRequest,
  issueLegacyDomainHandoff,
  legacyHandoffSessionCookieHeader,
  legacyHandoffSessionHeaders,
  legacyHandoffTarget,
  legacySignedSessionCookie,
  parseLegacyHandoffId,
  transferableAuthSession,
} from "../server/auth/legacy-domain-handoff.ts";
import { SECURE_AUTH_SESSION_COOKIE_NAME } from "../server/auth/cookie-names.ts";

type StoredRow = { expiresAt: number; value: string };

function createHandoffDb() {
  const rows = new Map<string, StoredRow>();
  const db = {
    prepare(sql: string) {
      return {
        bind(...values: unknown[]) {
          return {
            async run() {
              if (sql.startsWith('DELETE FROM "verification" WHERE "identifier" LIKE')) {
                const [prefix, now] = values as [string, number];
                for (const [identifier, row] of rows) {
                  if (identifier.startsWith(prefix.slice(0, -1)) && row.expiresAt <= now) rows.delete(identifier);
                }
                return {};
              }
              if (sql.startsWith('INSERT INTO "verification"')) {
                const [id, identifier, value, expiresAt] = values as [string, string, string, number];
                assert.equal(id.length, 36);
                rows.set(identifier, { expiresAt, value });
                return {};
              }
              throw new Error(`unexpected run: ${sql}`);
            },
            async first<T>() {
              if (!sql.startsWith('DELETE FROM "verification" WHERE "identifier" =')) {
                throw new Error(`unexpected first: ${sql}`);
              }
              const [identifier, now] = values as [string, number];
              const row = rows.get(identifier);
              if (!row || row.expiresAt <= now) return null;
              rows.delete(identifier);
              return { value: row.value } as T;
            },
          };
        },
      };
    },
  } as unknown as Pick<D1Database, "prepare">;
  return { db, rows };
}

const handoffId = "7f6e5d4c-3b2a-1908-7f6e-5d4c3b2a1908";
const sessionCookie = `${"a".repeat(32)}.${"b".repeat(32)}`;

test("legacy handoff keeps only a safe route and is consumed exactly once", async () => {
  const { db } = createHandoffDb();
  await issueLegacyDomainHandoff(db, { sessionCookie, targetPath: "/?view=period" }, 1_000, handoffId);

  assert.deepEqual(await consumeLegacyDomainHandoff(db, handoffId, 1_001), {
    sessionCookie,
    targetPath: "/?view=period",
  });
  assert.equal(await consumeLegacyDomainHandoff(db, handoffId, 1_002), null);
});

test("expired or malformed handoffs never produce a session transfer", async () => {
  const { db } = createHandoffDb();
  await issueLegacyDomainHandoff(db, { sessionCookie, targetPath: "https://outside.example.test" }, 0, handoffId);

  assert.equal(await consumeLegacyDomainHandoff(db, handoffId, LEGACY_DOMAIN_HANDOFF_TTL_MS + 1), null);
  assert.equal(parseLegacyHandoffId("not-a-handoff"), null);
  assert.equal(legacyHandoffTarget("https://outside.example.test"), "/");
  assert.equal(legacyHandoffTarget("//outside.example.test"), "/");
  assert.equal(legacyHandoffTarget("/\\outside"), "/");
  assert.equal(canonicalHandoffDestination("/?view=period"), "https://mydairy.linzezhang.com/?view=period");
});

test("handoff accepts only the precise old-to-new browser origins", () => {
  const oldOrigin = "https://huchuliang-workbench.linzezhang35.chatgpt.site";
  const canonicalOrigin = "https://mydairy.linzezhang.com";
  const issue = new Request(`${oldOrigin}/api/auth/legacy-domain-handoff`, {
    method: "POST",
    headers: { Origin: oldOrigin },
  });
  const complete = new Request(`${canonicalOrigin}/api/auth/legacy-domain-handoff/complete`, {
    method: "POST",
    headers: { Origin: oldOrigin },
  });
  const forged = new Request(`${canonicalOrigin}/api/auth/legacy-domain-handoff`, {
    method: "POST",
    headers: { Origin: "https://attacker.example.test" },
  });

  assert.equal(isRetiredHandoffIssuanceRequest(issue), true);
  assert.equal(isCanonicalHandoffCompletionRequest(complete), true);
  assert.equal(isRetiredHandoffIssuanceRequest(forged), false);
  assert.equal(isCanonicalHandoffCompletionRequest(forged), false);
});

test("only the configured signed Better Auth cookie is moved into a first-party canonical cookie", () => {
  const headers = new Headers({ Cookie: `${SECURE_AUTH_SESSION_COOKIE_NAME}=${sessionCookie}; unrelated=value` });
  assert.equal(legacySignedSessionCookie(headers), sessionCookie);
  assert.equal(legacySignedSessionCookie(new Headers({ Cookie: `${SECURE_AUTH_SESSION_COOKIE_NAME}=bad;` })), null);
  assert.equal(legacySignedSessionCookie(new Headers({ Cookie: `__Secure-better-auth.session_token=${sessionCookie};` })), null);
  assert.equal(
    legacyHandoffSessionHeaders(sessionCookie)?.get("cookie"),
    `${SECURE_AUTH_SESSION_COOKIE_NAME}=${sessionCookie}`,
  );
  const setCookie = legacyHandoffSessionCookieHeader(sessionCookie, 11_000, 1_000);
  assert.ok((setCookie ?? "").startsWith(`${SECURE_AUTH_SESSION_COOKIE_NAME}=`));
  assert.match(setCookie ?? "", /HttpOnly/);
  assert.match(setCookie ?? "", /Secure/);
  assert.match(setCookie ?? "", /SameSite=Lax/);
  assert.doesNotMatch(setCookie ?? "", /Domain=/);
});

test("only a server-authenticated session can complete a handoff", () => {
  assert.equal(transferableAuthSession({ session: { expiresAt: new Date() }, user: { id: "user-a" } }), true);
  assert.equal(transferableAuthSession({ session: {}, user: { id: "user-a" } }), true);
  assert.equal(transferableAuthSession({ session: { expiresAt: new Date() }, user: {} }), false);
  assert.equal(transferableAuthSession(null), false);
});

test("canonical completion keeps a retired anonymous history handoff in browser storage only", async () => {
  const oldOrigin = "https://huchuliang-workbench.linzezhang35.chatgpt.site";
  const canonicalOrigin = "https://mydairy.linzezhang.com";
  const [{ POST }, { serializeLegacyDeviceHistoryPayload }] = await Promise.all([
    import("../app/api/auth/legacy-domain-handoff/complete/route.ts"),
    import("../app/_components/workbench/legacy-device-history-payload.ts"),
  ]);
  const historyPayload = serializeLegacyDeviceHistoryPayload({
    sourceInstanceId: "guest-device-route-history-0001",
    sourceSchemaVersion: 1,
    exportedAt: "2026-08-13T00:00:00.000Z",
    modules: {
      diary: [{ id: "local_route_diary", localDate: "2026-08-13", body: "</script><script>throw new Error()</script>" }],
    },
    imageManifest: [],
  });
  assert.ok(historyPayload);

  const form = new FormData();
  form.set("history", historyPayload);
  form.set("next", "/?view=period");
  const response = await POST(new Request(canonicalOrigin + "/api/auth/legacy-domain-handoff/complete", {
    method: "POST",
    headers: { Origin: oldOrigin },
    body: form,
  }));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.ok((response.headers.get("content-security-policy") ?? "").includes("default-src"));
  const body = await response.text();
  assert.match(body, /sessionStorage\.setItem/);
  assert.match(body, /https:\/\/mydairy\.linzezhang\.com\/\?view=period/);
  assert.equal(body.includes("</script><script>"), false);
  assert.equal(body.includes("\\u003c/script"), true);
});
