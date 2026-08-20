import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import {
  ACCOUNT_PRIVACY_NOTICE_SHA256,
  ACCOUNT_PRIVACY_POLICY_VERSION,
  AccountInputError,
  getPrivacyState,
  parsePrivacyInput,
  setPrivacyConsent,
} from "../server/data/account-lifecycle.ts";
import {
  SensitiveCloudConsentRequiredError,
  requireSensitiveCloudConsent,
} from "../server/security/privacy-consent.ts";

type PrivacyDb = Pick<Parameters<typeof getPrivacyState>[0], "prepare">;

type BoundResult = Pick<SqlPreparedStatement, "bind" | "run" | "first" | "all" | "raw">;

type D1Mock = Pick<PrivacyDb, "prepare">;

function emptyMeta(changes = 0) {
  return {
    duration: 0,
    size_after: 0,
    rows_read: 0,
    rows_written: 0,
    last_row_id: 0,
    changes,
    changed_db: true,
  } as const;
}

function asD1Mock(db: DatabaseSync): D1Mock {
  return {
    prepare(sql) {
      const statement = db.prepare(sql);
      const executeBound = (...values: unknown[]): BoundResult => {
        const castRun = values as Parameters<(typeof statement)["run"]>;
        const castGet = values as Parameters<(typeof statement)["get"]>;
        const castAll = values as Parameters<(typeof statement)["all"]>;
        const normalizeBoolean = (value: unknown) => (typeof value === "boolean" ? (value ? 1 : 0) : value);
        const normalizedValues = castRun.map(normalizeBoolean) as Parameters<(typeof statement)["run"]>;

        return {
          bind: (...nextValues: unknown[]) => executeBound(...nextValues),
          run: (async () => {
            const result = statement.run(...normalizedValues);
            return { success: true, results: [], meta: emptyMeta(Number(result.changes ?? 0)) };
          }) as BoundResult["run"],
          first: (async () => {
            const row = statement.get(...castGet) as Record<string, unknown> | null;
            return row ?? null;
          }) as BoundResult["first"],
          all: (async () => {
            return {
              success: true,
              results: statement.all(...castAll) as Record<string, unknown>[],
              meta: emptyMeta(0),
            };
          }) as BoundResult["all"],
          raw: (() => Promise.resolve([[],] as [string[], ...unknown[]])) as BoundResult["raw"],
        };
      };

      return executeBound();
    },
  };
}

async function setupDb() {
  const db = new DatabaseSync(":memory:");
  const migrationOne = await readFile("drizzle/0001_auth_and_product.sql", "utf8");
  const migrationTwo = await readFile("drizzle/0002_s2_tenant_indexes.sql", "utf8");
  db.exec(migrationOne);
  db.exec(migrationTwo);
  const now = Date.now();
  db.prepare('INSERT INTO "user" (id, name, email, emailVerified, createdAt, updatedAt) VALUES (?, ?, ?, 1, ?, ?)')
    .run("user_privacy", "Privacy User", "privacy@example.test", now, now);
  return db;
}

test("parsePrivacyInput validates accepted/revoked payload", () => {
  assert.deepEqual(
    parsePrivacyInput({
      decision: "accepted",
      policyVersion: ACCOUNT_PRIVACY_POLICY_VERSION,
      noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
    }),
    {
      decision: "accepted",
      policyVersion: ACCOUNT_PRIVACY_POLICY_VERSION,
      noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
    },
  );

  assert.throws(
    () =>
      parsePrivacyInput({
        decision: "accepted",
        policyVersion: "x",
        noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
      }),
    (error): error is AccountInputError => error instanceof AccountInputError,
  );

  assert.throws(
    () =>
      parsePrivacyInput({
        decision: "accepted",
        policyVersion: ACCOUNT_PRIVACY_POLICY_VERSION,
        noticeSha256: "bad",
      }),
    (error): error is AccountInputError => error instanceof AccountInputError,
  );
});

test("setPrivacyConsent creates profile row when missing and writes consent event", async () => {
  const db = await setupDb();
  const d1 = asD1Mock(db);
  try {
    const first = await setPrivacyConsent(d1, "user_privacy", {
      decision: "accepted",
      policyVersion: ACCOUNT_PRIVACY_POLICY_VERSION,
      noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
    });
    assert.equal(first.privacyState, "accepted");
    const acceptedState = (db.prepare("SELECT privacy_consent_state, privacy_consented_at, privacy_revoked_at, privacy_policy_version FROM profile_settings WHERE user_id = ?")
      .get("user_privacy") as {
      privacy_consent_state: string;
      privacy_consented_at: number;
      privacy_revoked_at: number | null;
      privacy_policy_version: string;
    });
    assert.equal(acceptedState.privacy_consent_state, "accepted");
    assert.equal(acceptedState.privacy_policy_version, ACCOUNT_PRIVACY_POLICY_VERSION);
    assert.equal(acceptedState.privacy_consented_at > 0, true);
    assert.equal(acceptedState.privacy_revoked_at, null);

    const revoked = await setPrivacyConsent(d1, "user_privacy", {
      decision: "revoked",
      policyVersion: ACCOUNT_PRIVACY_POLICY_VERSION,
      noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
    });
    assert.equal(revoked.privacyState, "revoked");
    const revokedState = db
      .prepare("SELECT privacy_consent_state, privacy_consented_at, privacy_revoked_at, privacy_policy_version FROM profile_settings WHERE user_id = ?")
      .get("user_privacy") as {
      privacy_consent_state: string;
      privacy_consented_at: number;
      privacy_revoked_at: number;
      privacy_policy_version: string;
    };
    assert.equal(revokedState.privacy_consent_state, "revoked");
    assert.equal(revokedState.privacy_policy_version, ACCOUNT_PRIVACY_POLICY_VERSION);
    assert.equal(revokedState.privacy_revoked_at >= revokedState.privacy_consented_at, true);

    const snapshot = await getPrivacyState(d1, "user_privacy");
    assert.equal(snapshot.state, "revoked");
    assert.equal(snapshot.policyVersion, ACCOUNT_PRIVACY_POLICY_VERSION);
    assert.equal((snapshot.consentedAt ?? 0) > 0, true);
    assert.equal(snapshot.revokedAt !== null, true);
  } finally {
    db.close();
  }
});

test("sensitive cloud targets require an active opt-in and ordinary data remains available", async () => {
  const db = await setupDb();
  const d1 = asD1Mock(db);
  const sensitiveTargets = ["ledger", "weights", "diary", "periods"];
  try {
    for (const target of sensitiveTargets) {
      await assert.rejects(
        () => requireSensitiveCloudConsent(d1, "user_privacy", target),
        (error): error is SensitiveCloudConsentRequiredError => error instanceof SensitiveCloudConsentRequiredError,
      );
    }
    await requireSensitiveCloudConsent(d1, "user_privacy", "todos");
    await requireSensitiveCloudConsent(d1, "user_privacy", "food");

    await setPrivacyConsent(d1, "user_privacy", {
      decision: "accepted",
      policyVersion: "2026-08-02.v1",
      noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
    });
    await assert.rejects(
      () => requireSensitiveCloudConsent(d1, "user_privacy", "diary"),
      (error): error is SensitiveCloudConsentRequiredError => error instanceof SensitiveCloudConsentRequiredError,
    );

    await setPrivacyConsent(d1, "user_privacy", {
      decision: "accepted",
      policyVersion: ACCOUNT_PRIVACY_POLICY_VERSION,
      noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
    });
    for (const target of sensitiveTargets) {
      await requireSensitiveCloudConsent(d1, "user_privacy", target);
    }

    await setPrivacyConsent(d1, "user_privacy", {
      decision: "revoked",
      policyVersion: ACCOUNT_PRIVACY_POLICY_VERSION,
      noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
    });
    for (const target of sensitiveTargets) {
      await assert.rejects(
        () => requireSensitiveCloudConsent(d1, "user_privacy", target),
        (error): error is SensitiveCloudConsentRequiredError => error instanceof SensitiveCloudConsentRequiredError,
      );
    }
  } finally {
    db.close();
  }
});
