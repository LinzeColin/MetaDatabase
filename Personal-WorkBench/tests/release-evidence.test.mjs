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

test("Version 18 account-entry deployment evidence retains no account or runtime values", async () => {
  const evidence = JSON.parse(
    await readFile(new URL("../13_evidence/private_version_18_account_entry_deployment.json", import.meta.url), "utf8"),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.private_deployment.sites_version_number, 18);
  assert.equal(evidence.private_deployment.public_audience_changed, false);
  assert.equal(evidence.no_user_records_read_or_written, true);
  assert.equal(evidence.no_runtime_values_read, true);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("Bearer "), false);
  assert.equal(serialized.includes("token="), false);
});

test("Version 18 in-app mutation replay retains no session or record material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_18_agent_controlled_in_app_workbench_post_replay.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.current_private_version.sites_version_number, 18);
  assert.equal(evidence.mutation_attempt.workbench_write_response_observed, false);
  assert.equal(evidence.post_attempt_readback.habits_http_status, 200);
  assert.equal(evidence.post_attempt_readback.habit_checkins_http_status, 200);
  assert.equal(evidence.no_user_records_read_or_written, true);
  assert.equal(evidence.cleanup.temporary_browser_tab_finalized, true);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("Bearer "), false);
  assert.equal(serialized.includes("token="), false);
});

test("Version 18 Chrome auth and workbench replay retains no controlled-account material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_18_agent_controlled_chrome_auth_and_workbench_post_replay.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.current_private_version.sites_version_number, 18);
  assert.equal(evidence.controlled_identity_and_authentication.verification_message_received, true);
  assert.equal(evidence.workbench_replay.visible_business_record_creation_confirmed, false);
  assert.equal(evidence.cleanup.test_account_deletion_confirmed, true);
  assert.equal(evidence.cleanup.temporary_mailbox_deleted, true);
  assert.equal(evidence.cleanup.temporary_credentials_and_mail_references_cleared, true);
  assert.equal(evidence.cleanup.temporary_browser_tabs_finalized, true);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
  assert.equal(serialized.includes("PwB!"), false);
});

test("Version 21 A/B tenant replay retains no test-account material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_21_ab_tenant_history_replay.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 21);
  assert.equal(evidence.execution_surface.two_distinct_temporary_email_accounts, true);
  assert.equal(evidence.execution_surface.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.tenant_and_history.account_b_cannot_see_account_a_generated_record, true);
  assert.equal(evidence.tenant_and_history.account_a_generated_record_visible_after_reauthentication, true);
  assert.equal(evidence.scope_and_cleanup.temporary_credentials_or_mail_references_retained_in_evidence, false);
  assert.equal(evidence.scope_and_cleanup.temporary_mailboxes_deleted, true);
  assert.equal(evidence.scope_and_cleanup.temporary_browser_tabs_finalized, true);
  assert.equal(evidence.scope_and_cleanup.temporary_credentials_cleared_from_test_runtime, true);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 21 partial auth recovery replay retains no provider or reset material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_21_auth_recovery_partial_replay.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 21);
  assert.equal(evidence.google_oauth.sign_in_action_reached_google_account_selection, true);
  assert.equal(evidence.google_oauth.successful_current_version_callback_and_session, false);
  assert.equal(evidence.email_password_recovery.password_reset_mail_delivery, "PASS");
  assert.equal(evidence.email_password_recovery.new_password_submission_by_agent, "NOT_PERFORMED");
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.temporary_credentials_or_mail_references_retained_in_evidence, false);
  assert.equal(evidence.scope_and_cleanup.temporary_mailbox_deleted, true);
  assert.equal(evidence.scope_and_cleanup.temporary_browser_tabs_finalized, true);
  assert.equal(evidence.scope_and_cleanup.temporary_credentials_cleared_from_test_runtime, true);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 21 rollback and restore rehearsal retains no deployment or access identity material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_21_rollback_restore_rehearsal.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 21);
  assert.equal(evidence.rollback.target_version_number, 18);
  assert.equal(evidence.rollback.deployment_status, "SUCCEEDED");
  assert.equal(evidence.restore.target_version_number, 21);
  assert.equal(evidence.restore.deployment_status, "SUCCEEDED");
  assert.equal(evidence.restore.final_live_version_matches_restore_target, true);
  assert.equal(evidence.change_boundary.access_policy_changed, false);
  assert.equal(evidence.change_boundary.public_audience_changed, false);
  assert.equal(evidence.change_boundary.deployment_or_version_ids_recorded, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 22 sign-out replay retains no temporary identity or session material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_22_signout_session_recovery_partial_replay.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 22);
  assert.equal(evidence.local_validation.auth_contract, "PASS_19_OF_19");
  assert.equal(evidence.private_deployment.deployment_status, "SUCCEEDED");
  assert.equal(evidence.controlled_browser_replay.account_sign_out_control_visible_on_version_22, true);
  assert.equal(evidence.controlled_browser_replay.temporary_identity_confirmed_before_mutation, false);
  assert.equal(evidence.controlled_browser_replay.sign_out_click_performed, false);
  assert.equal(evidence.scope_and_cleanup.temporary_mailbox_deleted, true);
  assert.equal(evidence.scope_and_cleanup.temporary_browser_tabs_finalized, true);
  assert.equal(evidence.scope_and_cleanup.temporary_credentials_cleared_from_test_runtime, true);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 23 brand-domain deployment retains no sensitive deployment material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_23_brand_domain_normalization.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 23);
  assert.equal(evidence.local_validation.canonical_domain_contract, "PASS_3_OF_3");
  assert.equal(evidence.brand_and_domain.display_name, "个人日程");
  assert.equal(evidence.brand_and_domain.technical_slug, "mydairy");
  assert.equal(evidence.brand_and_domain.custom_domain_status, "ACTIVE");
  assert.equal(evidence.private_deployment.deployment_status, "SUCCEEDED");
  assert.equal(evidence.private_deployment.public_audience_changed, false);
  assert.equal(evidence.change_boundary.temporary_deployment_archive_removed, true);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});
