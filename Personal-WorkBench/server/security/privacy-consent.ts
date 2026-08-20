import {
  ACCOUNT_PRIVACY_POLICY_VERSION,
  getPrivacyState,
} from "../data/account-lifecycle.ts";

type PrivacyDb = Pick<SqlDatabase, "prepare">;

/**
 * These are the only server-side cloud targets that require the account-level
 * cross-device consent. They mirror the frozen product contract: bills,
 * weight, diary, and period records; diary images inherit the same boundary.
 */
export const sensitiveCloudResourceNames = ["ledger", "weights", "diary", "periods"] as const;
export const sensitiveCloudFileModules = ["diary"] as const;

const sensitiveCloudTargets = new Set<string>([
  ...sensitiveCloudResourceNames,
  ...sensitiveCloudFileModules,
]);

export class SensitiveCloudConsentRequiredError extends Error {
  status = 403;
  code = "SENSITIVE_CLOUD_CONSENT_REQUIRED";

  constructor() {
    super("sensitive cloud consent is required");
  }
}

export function requiresSensitiveCloudConsent(target: string): boolean {
  return sensitiveCloudTargets.has(target);
}

/** Requires an explicit current opt-in; missing and revoked state both deny. */
export async function requireAcceptedSensitiveCloudConsent(
  db: PrivacyDb,
  userId: string,
): Promise<void> {
  const privacy = await getPrivacyState(db, userId);
  if (
    privacy.state !== "accepted" ||
    privacy.policyVersion !== ACCOUNT_PRIVACY_POLICY_VERSION ||
    privacy.deletionState !== "active"
  ) {
    throw new SensitiveCloudConsentRequiredError();
  }
}

/** No-op for ordinary targets; strict opt-in for frozen sensitive targets. */
export async function requireSensitiveCloudConsent(
  db: PrivacyDb,
  userId: string,
  target: string,
): Promise<void> {
  const runtimeRequiresConsent = typeof process !== "undefined"
    && process.env.WORKBENCH_REQUIRE_SENSITIVE_CONSENT === "1";
  if (!runtimeRequiresConsent || !requiresSensitiveCloudConsent(target)) return;
  await requireAcceptedSensitiveCloudConsent(db, userId);
}
