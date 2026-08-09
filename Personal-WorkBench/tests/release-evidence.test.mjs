import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { evidenceReference, redactCommandResult } from "../scripts/verify-release.mjs";

test("release evidence stores command status without raw command output", () => {
  const result = redactCommandResult({
    name: "quality",
    command: "npm run test:quality",
    status: 0,
    signal: null,
    ok: true,
    stdout: "SENTINEL_RELEASE_OUTPUT",
    stderr: "SENTINEL_RELEASE_ERROR",
  });

  const serialized = JSON.stringify(result);
  assert.equal(serialized.includes("SENTINEL_RELEASE"), false);
  assert.equal("stdout" in result, false);
  assert.equal("stderr" in result, false);
  assert.equal(result.output_redacted, true);
});

test("release evidence references do not retain nested raw evidence", () => {
  const reference = evidenceReference(
    {
      exists: true,
      status: "PASS_LOCAL_QUALITY",
      phase: "S4-T1",
      runAt: "2026-08-09T00:00:00.000Z",
      raw: { secret: "SENTINEL_EVIDENCE_SECRET" },
    },
    "13_evidence/quality.json",
  );

  const serialized = JSON.stringify(reference);
  assert.equal(serialized.includes("SENTINEL_"), false);
  assert.equal("raw" in reference, false);
  assert.equal(reference.source, "13_evidence/quality.json");
});

test("controlled browser replay evidence does not retain test credentials", async () => {
  const evidence = JSON.parse(
    await readFile(new URL("../13_evidence/ordinary_chrome_auth_replay.json", import.meta.url), "utf8"),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("invalid reset replay evidence does not retain temporary reset material", async () => {
  const evidence = JSON.parse(
    await readFile(new URL("../13_evidence/invalid_reset_token_server_rejection_replay.json", import.meta.url), "utf8"),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(evidence.replay.temporary_password_cleared, true);
  assert.equal(evidence.replay.temporary_browser_tab_closed, true);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
  assert.equal(serialized.includes("Pwb!"), false);
});

test("Version 17 negative reset replay retains no mailbox identity", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_17_negative_password_reset_non_enumeration_replay.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.current_private_version.sites_version_number, 17);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(evidence.replay.controlled_alias_mailbox_baseline_count, 0);
  assert.equal(evidence.replay.controlled_alias_mailbox_immediate_count, 0);
  assert.equal(evidence.replay.controlled_alias_mailbox_delayed_count, 0);
  assert.equal(evidence.replay.bounded_mailbox_readback_wait_seconds, 30);
  assert.equal(evidence.replay.test_input_cleared, true);
  assert.equal(evidence.replay.temporary_browser_tab_closed, true);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
  assert.equal(serialized.includes("Pwb!"), false);
});

test("Version 17 ordinary desktop boundary evidence retains no login material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_17_ordinary_desktop_browser_access_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.current_private_version.sites_version_number, 17);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(evidence.observations.email_or_password_entered, false);
  assert.equal(evidence.observations.account_selection_attempted, false);
  assert.equal(evidence.observations.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.observations.temporary_desktop_tab_closed, true);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("code_challenge"), false);
  assert.equal(serialized.includes("nonce="), false);
  assert.equal(serialized.includes("state="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 17 storage-binding evidence retains no physical resource material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_17_storage_binding_reconciliation.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.current_private_version.sites_version_number, 17);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(evidence.site_control_plane.site_metadata_exposes_physical_d1_mapping, false);
  assert.equal(evidence.site_control_plane.site_metadata_exposes_physical_r2_mapping, false);
  assert.equal(evidence.result.d1_sql_executed, false);
  assert.equal(evidence.result.r2_objects_listed, false);
  assert.equal(serialized.includes("database_id"), false);
  assert.equal(serialized.includes("bucket_name"), false);
  assert.equal(serialized.includes("Bearer "), false);
  assert.equal(serialized.includes("@"), false);
});

test("Version 17 Chrome transport evidence retains no controlled-account material", async () => {
  const evidence = JSON.parse(
    await readFile(new URL("../13_evidence/version_17_agent_controlled_chrome_workbench_post_replay.json", import.meta.url), "utf8"),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(evidence.cleanup.test_account_deletion_confirmed, true);
  assert.equal(evidence.cleanup.temporary_credentials_and_mail_references_cleared, true);
  assert.equal(evidence.cleanup.temporary_browser_tabs_finalized, true);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
  assert.equal(serialized.includes("Pwb!"), false);
});
