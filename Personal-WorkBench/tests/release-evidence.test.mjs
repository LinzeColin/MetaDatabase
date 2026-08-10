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

test("Version 24 sign-out and session-recovery replay retains no temporary identity material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_24_signout_session_recovery_replay.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 24);
  assert.equal(evidence.root_cause_and_fix.prior_version_23_signout_response_status, 415);
  assert.equal(evidence.root_cause_and_fix.fixed_request_contract.content_type, "application/json");
  assert.equal(evidence.local_validation.auth_contract, "PASS_19_OF_19");
  assert.equal(evidence.private_deployment.deployment_status, "SUCCEEDED");
  assert.equal(evidence.controlled_browser_replay.temporary_identity_confirmed_before_v24_signout, true);
  assert.equal(evidence.controlled_browser_replay.v24_signout_redirected_to_neutral_confirmation, true);
  assert.equal(evidence.controlled_browser_replay.v24_relogin_reached_workspace, true);
  assert.equal(evidence.controlled_browser_replay.v24_session_recovery_account_identity_restored, true);
  assert.equal(evidence.scope_and_cleanup.temporary_mailbox_deleted, true);
  assert.equal(evidence.scope_and_cleanup.temporary_credentials_cleared_from_test_runtime, true);
  assert.equal(evidence.scope_and_cleanup.temporary_deployment_archive_removed, true);
  assert.equal(evidence.scope_and_cleanup.temporary_application_account_deletion_attempted, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 27 storage-binding health replay retains no account or storage material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_27_storage_binding_health_replay.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 27);
  assert.equal(evidence.private_deployment.deployment_status, "SUCCEEDED");
  assert.equal(evidence.local_validation.api_contract, "PASS_7_OF_7");
  assert.equal(evidence.local_validation.storage_binding_probe_unit, "PASS_2_OF_2");
  assert.equal(evidence.local_validation.r2_contract, "PASS_4_OF_4");
  assert.equal(evidence.probe_scope.product_tables_read, false);
  assert.equal(evidence.probe_scope.r2_object_body_read, false);
  assert.equal(evidence.probe_scope.r2_object_listed, false);
  assert.equal(evidence.probe_scope.r2_object_written, false);
  assert.equal(evidence.probe_scope.r2_object_deleted, false);
  assert.equal(evidence.controlled_browser_replay.d1_available, true);
  assert.equal(evidence.controlled_browser_replay.r2_available, true);
  assert.equal(evidence.scope_and_cleanup.temporary_mailbox_deleted, true);
  assert.equal(evidence.scope_and_cleanup.temporary_credentials_cleared_from_test_runtime, true);
  assert.equal(evidence.scope_and_cleanup.temporary_browser_tabs_finalized, true);
  assert.equal(evidence.scope_and_cleanup.temporary_deployment_archives_removed, true);
  assert.equal(evidence.result.direct_physical_d1_r2_reconciliation_proven, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 28 brand-identity deployment retains no source credential or user data", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_28_brand_identity_reconciliation.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 28);
  assert.equal(evidence.candidate.source_projection_tree_matches_local_project_tree, true);
  assert.equal(evidence.local_validation.canonical_domain_contract, "PASS_3_OF_3");
  assert.equal(evidence.local_validation.outbox_migration_contract, "PASS_7_OF_7");
  assert.equal(evidence.brand_and_domain.display_name, "个人日程");
  assert.equal(evidence.brand_and_domain.technical_slug, "mydairy");
  assert.equal(evidence.brand_and_domain.custom_domain_status, "ACTIVE");
  assert.equal(evidence.private_deployment.deployment_status, "SUCCEEDED");
  assert.equal(evidence.private_deployment.public_audience_changed, false);
  assert.equal(evidence.change_boundary.authentication_logic_changed, false);
  assert.equal(evidence.change_boundary.tenant_or_persistence_logic_changed, false);
  assert.equal(evidence.change_boundary.real_user_business_data_read_or_written, false);
  assert.equal(evidence.change_boundary.temporary_deployment_archive_removed, true);
  assert.equal(evidence.change_boundary.temporary_source_credentials_cleared_from_agent_runtime, true);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 29 local-first deployment retains no source credential or user data", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_29_local_first_persistence_deployment.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 29);
  assert.equal(evidence.candidate.source_projection_tree_matches_local_project_tree, true);
  assert.equal(evidence.candidate.source_push_mode, "NON_FORCE_FAST_FORWARD");
  assert.equal(evidence.local_validation.workbench_data_contract, "PASS_12_OF_12");
  assert.equal(evidence.private_deployment.deployment_status, "SUCCEEDED");
  assert.equal(evidence.private_deployment.public_audience_changed, false);
  assert.equal(evidence.change_boundary.authentication_logic_changed, false);
  assert.equal(evidence.change_boundary.tenant_or_persistence_logic_changed, true);
  assert.equal(evidence.change_boundary.runtime_environment_changed, false);
  assert.equal(evidence.change_boundary.real_user_business_data_read_or_written, false);
  assert.equal(evidence.change_boundary.temporary_deployment_archive_removed, true);
  assert.equal(evidence.change_boundary.temporary_source_credentials_cleared_from_agent_runtime, true);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 30 generic outbox deployment retains privacy and current-version boundaries", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_30_generic_outbox_deployment.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 30);
  assert.equal(evidence.candidate.source_projection_tree_matches_local_project_tree, true);
  assert.equal(evidence.candidate.source_push_mode, "NON_FORCE_FAST_FORWARD");
  assert.equal(evidence.local_validation.workbench_persistence_ui, "PASS_10_OF_10");
  assert.equal(evidence.local_validation.privacy_contract, "PASS_3_OF_3");
  assert.equal(evidence.local_validation.tenant_contract, "PASS_2_OF_2");
  assert.equal(evidence.private_deployment.deployment_status, "SUCCEEDED");
  assert.equal(evidence.private_deployment.environment_revision, 8);
  assert.equal(evidence.private_deployment.public_audience_changed, false);
  assert.equal(evidence.change_boundary.generic_non_sensitive_outbox_replay_enabled, true);
  assert.equal(evidence.change_boundary.generic_replay_is_scoped_to_the_same_known_account, true);
  assert.equal(evidence.change_boundary.guest_partition_auto_replay_enabled, false);
  assert.equal(evidence.change_boundary.sensitive_record_auto_replay_enabled, false);
  assert.equal(evidence.change_boundary.authentication_logic_changed, false);
  assert.equal(evidence.change_boundary.server_tenant_derivation_changed, false);
  assert.equal(evidence.change_boundary.runtime_environment_changed, false);
  assert.equal(evidence.change_boundary.d1_or_r2_binding_changed, false);
  assert.equal(evidence.change_boundary.access_policy_changed, false);
  assert.equal(evidence.change_boundary.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 31 account-scope refresh deployment retains private and current-version boundaries", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_31_account_scope_refresh_deployment.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 31);
  assert.equal(evidence.candidate.source_projection_tree_matches_local_project_tree, true);
  assert.equal(evidence.candidate.source_push_mode, "NON_FORCE_FAST_FORWARD");
  assert.equal(evidence.local_validation.local_record_cache_contract, "PASS_3_OF_3");
  assert.equal(evidence.local_validation.workbench_persistence_ui, "PASS_11_OF_11");
  assert.equal(evidence.local_validation.privacy_contract, "PASS_3_OF_3");
  assert.equal(evidence.local_validation.tenant_contract, "PASS_2_OF_2");
  assert.equal(evidence.local_validation.release_evidence_postdeployment, "PASS_41_OF_41");
  assert.equal(evidence.private_deployment.deployment_status, "SUCCEEDED");
  assert.equal(evidence.private_deployment.public_audience_changed, false);
  assert.equal(evidence.private_deployment.saved_version_source_readback_matches_pushed_projection, true);
  assert.equal(evidence.change_boundary.account_scope_rechecked_before_remote_read_create_delete_and_replay, true);
  assert.equal(evidence.change_boundary.scope_drift_discards_stale_remote_projection, true);
  assert.equal(evidence.change_boundary.focus_and_visible_refresh_rechecks_scope, true);
  assert.equal(evidence.change_boundary.authentication_logic_changed, false);
  assert.equal(evidence.change_boundary.server_tenant_derivation_changed, false);
  assert.equal(evidence.change_boundary.runtime_environment_changed, false);
  assert.equal(evidence.change_boundary.d1_or_r2_binding_changed, false);
  assert.equal(evidence.change_boundary.access_policy_changed, false);
  assert.equal(evidence.change_boundary.real_user_business_data_read_or_written, false);
  assert.equal(evidence.change_boundary.temporary_source_credentials_cleared_from_agent_runtime, true);
  assert.equal(evidence.change_boundary.temporary_deployment_archive_removed, true);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 31 storage-mapping boundary retains no physical resource or provider material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_31_storage_mapping_read_only_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 31);
  assert.equal(evidence.candidate.current_saved_version_source_matches_v31_deployment_evidence, true);
  assert.equal(evidence.candidate.public_audience_changed, false);
  assert.equal(evidence.current_control_plane.site_active, true);
  assert.equal(evidence.current_control_plane.current_user_role, "owner");
  assert.equal(evidence.current_control_plane.access_mode, "custom");
  assert.equal(evidence.current_control_plane.allowed_user_count, 1);
  assert.equal(evidence.current_control_plane.allowed_group_count, 0);
  assert.equal(evidence.current_control_plane.external_visitor_count, 0);
  assert.equal(evidence.current_control_plane.latest_saved_version_number, 31);
  assert.equal(evidence.current_control_plane.runtime_values_read, false);
  assert.equal(evidence.current_control_plane.source_credentials_read_or_used, false);
  assert.equal(evidence.current_control_plane.bypass_token_generated_or_used, false);
  assert.equal(evidence.sites_and_source_binding_surface.logical_d1_binding_name_present, true);
  assert.equal(evidence.sites_and_source_binding_surface.logical_r2_binding_name_present, true);
  assert.equal(evidence.sites_and_source_binding_surface.local_vite_d1_identifier_is_development_placeholder_only, true);
  assert.equal(evidence.sites_and_source_binding_surface.local_vite_r2_name_is_development_placeholder_only, true);
  assert.equal(evidence.sites_and_source_binding_surface.physical_d1_identifier_exposed_by_safe_surface, false);
  assert.equal(evidence.sites_and_source_binding_surface.physical_r2_identifier_exposed_by_safe_surface, false);
  assert.equal(evidence.catalogue_probe.wrangler_v4_or_newer, true);
  assert.equal(evidence.catalogue_probe.wrangler_identity_authenticated, true);
  assert.equal(evidence.catalogue_probe.d1_catalogue_accessible, false);
  assert.equal(evidence.catalogue_probe.r2_catalogue_accessible, false);
  assert.equal(evidence.catalogue_probe.physical_identifiers_recorded, false);
  assert.equal(evidence.catalogue_probe.raw_cli_output_recorded, false);
  assert.equal(evidence.catalogue_probe.provider_error_text_recorded, false);
  assert.equal(evidence.catalogue_probe.temporary_output_cleanup_verified, true);
  assert.equal(evidence.local_validation.lint, "PASS");
  assert.equal(evidence.local_validation.release_evidence, "PASS_44_OF_44");
  assert.equal(evidence.local_validation.release_verifier, "PASS_BUILD_LAST_MILE_READINESS");
  assert.equal(evidence.local_validation.diff_check, "PASS");
  assert.equal(evidence.result.direct_d1_r2_reconciliation_proven, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.scope_and_cleanup.d1_sql_or_r2_object_operation_executed, false);
  assert.equal(evidence.scope_and_cleanup.d1_or_r2_resource_configuration_changed, false);
  assert.equal(evidence.scope_and_cleanup.access_policy_or_public_audience_changed, false);
  assert.equal(evidence.scope_and_cleanup.temporary_raw_cli_output_destroyed, true);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("database_id"), false);
  assert.equal(serialized.includes("bucket_name"), false);
  assert.equal(serialized.includes("Bearer "), false);
  assert.equal(serialized.includes("@"), false);
});

test("Version 31 rollback and restore rehearsal retains no deployment or user material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_31_rollback_restore_rehearsal.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.approved_sites_version_number, 31);
  assert.equal(evidence.candidate.previous_saved_sites_version_number, 30);
  assert.equal(evidence.private_access_precondition.latest_saved_version_number, 31);
  assert.equal(evidence.execution.private_deploy_previous_version_succeeded, true);
  assert.equal(evidence.execution.private_restore_approved_version_succeeded, true);
  assert.equal(evidence.execution.deployment_identifiers_recorded, false);
  assert.equal(evidence.execution.deployment_urls_recorded, false);
  assert.equal(evidence.execution.failure_messages_recorded, false);
  assert.equal(evidence.post_restore_control_plane.latest_saved_version_number, 31);
  assert.equal(evidence.post_restore_control_plane.approved_version_source_matches_expected, true);
  assert.equal(evidence.post_restore_control_plane.external_visitor_count, 0);
  assert.equal(evidence.local_validation.lint, "PASS");
  assert.equal(evidence.local_validation.release_evidence, "PASS_45_OF_45");
  assert.equal(evidence.local_validation.release_verifier, "PASS_BUILD_LAST_MILE_READINESS");
  assert.equal(evidence.local_validation.diff_check, "PASS");
  assert.equal(evidence.result.current_v31_rollback_then_restore_proven, true);
  assert.equal(evidence.result.product_pass_claimed, false);
  assert.equal(evidence.result.final_acceptance_claimed, false);
  assert.equal(evidence.result.public_deploy_eligible, false);
  assert.equal(evidence.scope_and_cleanup.runtime_values_read, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.scope_and_cleanup.d1_or_r2_resource_configuration_changed, false);
  assert.equal(evidence.scope_and_cleanup.access_policy_changed, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 31 email browser boundary retains no mailbox, account, or navigation material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_31_email_browser_security_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 31);
  assert.equal(evidence.controlled_browser_attempt.fresh_agent_test_tab_created, true);
  assert.equal(evidence.controlled_browser_attempt.existing_user_tab_claimed, false);
  assert.equal(evidence.controlled_browser_attempt.target_route, "/auth/sign-up");
  assert.equal(evidence.controlled_browser_attempt.navigation_completed, false);
  assert.equal(evidence.controlled_browser_attempt.signup_page_rendered, false);
  assert.equal(evidence.controlled_browser_attempt.navigation_security_boundary_observed, true);
  assert.equal(evidence.controlled_browser_attempt.navigation_failure_cause_determined, false);
  assert.equal(evidence.controlled_browser_attempt.retry_or_browser_switch_used_to_bypass_boundary, false);
  assert.equal(evidence.controlled_browser_attempt.bypass_token_generated_or_used, false);
  assert.equal(evidence.controlled_browser_attempt.account_or_email_entered, false);
  assert.equal(evidence.controlled_browser_attempt.credential_entered, false);
  assert.equal(evidence.scope_and_cleanup.gmail_connector_used, false);
  assert.equal(evidence.scope_and_cleanup.mailbox_content_or_identity_recorded, false);
  assert.equal(evidence.scope_and_cleanup.mailbox_search_or_read_in_this_increment, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.temporary_test_tab_finalized, true);
  assert.equal(evidence.scope_and_cleanup.temporary_application_account_created, false);
  assert.equal(evidence.result.current_v31_email_registration_verification_reset_signin_proven, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 31 Google browser boundary retains no account, session, or navigation material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_31_google_oauth_browser_security_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 31);
  assert.equal(evidence.controlled_browser_attempt.fresh_agent_test_tab_created, true);
  assert.equal(evidence.controlled_browser_attempt.existing_user_tab_claimed, false);
  assert.equal(evidence.controlled_browser_attempt.target_route, "/auth/sign-in");
  assert.equal(evidence.controlled_browser_attempt.navigation_completed, false);
  assert.equal(evidence.controlled_browser_attempt.signin_page_rendered, false);
  assert.equal(evidence.controlled_browser_attempt.navigation_security_boundary_observed, true);
  assert.equal(evidence.controlled_browser_attempt.navigation_failure_cause_determined, false);
  assert.equal(evidence.controlled_browser_attempt.retry_or_browser_switch_used_to_bypass_boundary, false);
  assert.equal(evidence.controlled_browser_attempt.bypass_token_generated_or_used, false);
  assert.equal(evidence.controlled_browser_attempt.google_account_selection_attempted, false);
  assert.equal(evidence.controlled_browser_attempt.credential_entered, false);
  assert.equal(evidence.google_oauth.account_selection_attempted, false);
  assert.equal(evidence.google_oauth.google_callback_observed, false);
  assert.equal(evidence.google_oauth.application_session_established, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.temporary_test_tab_finalized, true);
  assert.equal(evidence.result.current_v31_google_callback_and_session_proven, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 30 email browser boundary retains no mailbox, account, or navigation material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_30_email_browser_navigation_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 30);
  assert.equal(evidence.controlled_browser_attempt.fresh_agent_test_tab_created, true);
  assert.equal(evidence.controlled_browser_attempt.target_route, "/auth/sign-up");
  assert.equal(evidence.controlled_browser_attempt.navigation_completed, false);
  assert.equal(evidence.controlled_browser_attempt.signup_page_rendered, false);
  assert.equal(evidence.controlled_browser_attempt.navigation_security_boundary_observed, true);
  assert.equal(evidence.controlled_browser_attempt.navigation_failure_cause_determined, false);
  assert.equal(evidence.controlled_browser_attempt.retry_or_browser_switch_used_to_bypass_boundary, false);
  assert.equal(evidence.controlled_browser_attempt.bypass_token_generated_or_used, false);
  assert.equal(evidence.controlled_browser_attempt.account_or_email_entered, false);
  assert.equal(evidence.controlled_browser_attempt.credential_entered, false);
  assert.equal(evidence.scope_and_cleanup.mailbox_content_or_identity_recorded, false);
  assert.equal(evidence.scope_and_cleanup.mailbox_search_or_read_in_this_increment, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.temporary_test_tab_finalized, true);
  assert.equal(evidence.scope_and_cleanup.temporary_application_account_created, false);
  assert.equal(evidence.result.current_v30_email_registration_verification_reset_signin_proven, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 30 email browser boundary recheck retains no mailbox, account, or navigation material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_30_email_browser_security_boundary_recheck.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 30);
  assert.equal(evidence.controlled_browser_attempt.fresh_agent_test_tab_created, true);
  assert.equal(evidence.controlled_browser_attempt.target_route, "/auth/sign-up");
  assert.equal(evidence.controlled_browser_attempt.navigation_completed, false);
  assert.equal(evidence.controlled_browser_attempt.signup_page_rendered, false);
  assert.equal(evidence.controlled_browser_attempt.navigation_security_boundary_observed, true);
  assert.equal(evidence.controlled_browser_attempt.navigation_failure_cause_determined, false);
  assert.equal(evidence.controlled_browser_attempt.retry_or_browser_switch_used_to_bypass_boundary, false);
  assert.equal(evidence.controlled_browser_attempt.bypass_token_generated_or_used, false);
  assert.equal(evidence.controlled_browser_attempt.account_or_email_entered, false);
  assert.equal(evidence.controlled_browser_attempt.credential_entered, false);
  assert.equal(evidence.scope_and_cleanup.gmail_connector_used, false);
  assert.equal(evidence.scope_and_cleanup.mailbox_content_or_identity_recorded, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.temporary_test_tab_finalized, true);
  assert.equal(evidence.scope_and_cleanup.temporary_application_account_created, false);
  assert.equal(evidence.result.current_v30_email_registration_verification_reset_signin_proven, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 30 Google browser boundary retains no account, session, or navigation material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_30_google_oauth_browser_security_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 30);
  assert.equal(evidence.control_plane_precondition.site_active, true);
  assert.equal(evidence.control_plane_precondition.current_user_role_owner, true);
  assert.equal(evidence.control_plane_precondition.access_mode_custom, true);
  assert.equal(evidence.control_plane_precondition.allowed_user_count, 1);
  assert.equal(evidence.control_plane_precondition.allowed_group_count, 0);
  assert.equal(evidence.control_plane_precondition.external_visitor_count, 0);
  assert.equal(evidence.control_plane_precondition.latest_saved_version_number, 30);
  assert.equal(evidence.control_plane_precondition.latest_saved_version_source_matches_expected, true);
  assert.equal(evidence.controlled_browser_attempt.fresh_agent_test_tab_created, true);
  assert.equal(evidence.controlled_browser_attempt.target_route, "/auth/sign-in");
  assert.equal(evidence.controlled_browser_attempt.navigation_completed, false);
  assert.equal(evidence.controlled_browser_attempt.signin_page_rendered, false);
  assert.equal(evidence.controlled_browser_attempt.page_content_inspected, false);
  assert.equal(evidence.controlled_browser_attempt.navigation_security_boundary_observed, true);
  assert.equal(evidence.controlled_browser_attempt.navigation_failure_cause_determined, false);
  assert.equal(evidence.controlled_browser_attempt.google_authorization_entry_attempted, false);
  assert.equal(evidence.controlled_browser_attempt.google_account_selection_observed, false);
  assert.equal(evidence.controlled_browser_attempt.google_callback_observed, false);
  assert.equal(evidence.controlled_browser_attempt.application_session_observed, false);
  assert.equal(evidence.controlled_browser_attempt.retry_or_browser_switch_used_to_bypass_boundary, false);
  assert.equal(evidence.controlled_browser_attempt.bypass_token_generated_or_used, false);
  assert.equal(evidence.controlled_browser_attempt.personal_google_account_or_credential_used, false);
  assert.equal(evidence.controlled_browser_attempt.raw_navigation_error_recorded, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.temporary_test_tab_finalized, true);
  assert.equal(evidence.scope_and_cleanup.temporary_application_account_created, false);
  assert.equal(evidence.result.current_v30_google_oauth_callback_or_session_proven, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 30 S5-T3 gate audit keeps current production proof distinct from historical support", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_30_s5_t3_gate_audit.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 30);
  assert.equal(evidence.frozen_taskpack_binding.task_dag_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.acceptance_contract_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.oracles_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.traceability_matrix_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.owner_approval_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.sequence_addendum_validation, "PASS_SEQUENCE_ADDENDUM_INTEGRITY_ONLY");
  assert.equal(evidence.frozen_taskpack_binding.requirement_count, 15);
  assert.equal(evidence.current_control_plane.latest_saved_version_number, 30);
  assert.equal(evidence.current_control_plane.latest_saved_version_source_matches_expected, true);
  assert.equal(evidence.gate_assessment.r003_real_authentication.status, "PARTIAL");
  assert.equal(
    evidence.gate_assessment.r003_real_authentication.current_v30_google_callback_and_session,
    "NOT_PROVEN_FRESH_AGENT_TEST_TAB_SECURITY_BOUNDARY_BEFORE_SIGNIN_RENDER",
  );
  assert.equal(evidence.gate_assessment.r004_a_b_isolation.current_v30_physical_a_b_replay, "NOT_RUN");
  assert.equal(
    evidence.gate_assessment.r005_d1_r2_persistence.current_v30_physical_mapping_or_record_object_reconciliation,
    "NOT_PROVEN",
  );
  assert.equal(evidence.gate_assessment.r009_saved_version_rollback_restore.status, "PASS");
  assert.equal(
    evidence.gate_assessment.r009_saved_version_rollback_restore.current_v30_rollback_then_restore,
    "PASS_PRIVATE_VERSION_30_TO_29_TO_30_OWNER_ONLY",
  );
  assert.equal(evidence.gate_assessment.r011_cross_device_crud_and_history.current_v30_physical_cross_device_history, "NOT_RUN");
  assert.equal(evidence.gate_assessment.r014_production_recovery.status, "PARTIAL");
  assert.equal(evidence.gate_assessment.physical_second_device_history.status, "NOT_RUN");
  assert.equal(evidence.result.s5_t3_core_chains_all_pass, false);
  assert.equal(evidence.result.s5_t3_threshold_met, false);
  assert.equal(evidence.result.public_deploy_eligible, false);
  assert.equal(evidence.scope_and_cleanup.taskpack_source_modified, false);
  assert.equal(evidence.scope_and_cleanup.sites_control_plane_read_only, true);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 30 rollback and restore rehearsal retains no deployment or user material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_30_rollback_restore_rehearsal.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.approved_sites_version_number, 30);
  assert.equal(evidence.candidate.previous_saved_sites_version_number, 29);
  assert.equal(evidence.execution.private_deploy_previous_version_succeeded, true);
  assert.equal(evidence.execution.private_restore_approved_version_succeeded, true);
  assert.equal(evidence.post_restore_control_plane.latest_saved_version_number, 30);
  assert.equal(evidence.post_restore_control_plane.approved_version_source_matches_expected, true);
  assert.equal(evidence.post_restore_control_plane.environment_revision, 8);
  assert.equal(evidence.post_restore_control_plane.external_visitor_count, 0);
  assert.equal(evidence.result.current_v30_rollback_then_restore_proven, true);
  assert.equal(evidence.execution.deployment_identifiers_recorded, false);
  assert.equal(evidence.scope_and_cleanup.runtime_values_read, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 30 post-restore error check retains no worker log material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_30_post_restore_error_log_check.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 30);
  assert.equal(evidence.read_only_query.errors_only, true);
  assert.equal(evidence.read_only_query.since_minutes, 10);
  assert.equal(evidence.read_only_query.worker_error_event_count, 0);
  assert.equal(evidence.read_only_query.raw_log_messages_recorded, false);
  assert.equal(evidence.result.post_restore_narrow_error_only_window_has_visible_p0, false);
  assert.equal(evidence.result.current_v30_production_p0_absence_fully_proven, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 30 storage-mapping boundary retains no physical resource or provider material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_30_storage_mapping_read_only_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 30);
  assert.equal(evidence.sites_and_source_binding_surface.logical_d1_binding_name_present, true);
  assert.equal(evidence.sites_and_source_binding_surface.logical_r2_binding_name_present, true);
  assert.equal(evidence.sites_and_source_binding_surface.physical_d1_identifier_exposed_by_safe_surface, false);
  assert.equal(evidence.sites_and_source_binding_surface.physical_r2_identifier_exposed_by_safe_surface, false);
  assert.equal(evidence.catalogue_probe.wrangler_v4_or_newer, true);
  assert.equal(evidence.catalogue_probe.wrangler_identity_authenticated, true);
  assert.equal(evidence.catalogue_probe.d1_catalogue_accessible, false);
  assert.equal(evidence.catalogue_probe.r2_catalogue_accessible, false);
  assert.equal(evidence.catalogue_probe.physical_identifiers_recorded, false);
  assert.equal(evidence.result.direct_d1_r2_reconciliation_proven, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("database_id"), false);
  assert.equal(serialized.includes("bucket_name"), false);
  assert.equal(serialized.includes("Bearer "), false);
  assert.equal(serialized.includes("@"), false);
});

test("Version 29 Google browser boundary retains no account or browser material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_29_google_oauth_browser_navigation_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 29);
  assert.equal(evidence.in_app_browser.signin_page_rendered, false);
  assert.equal(evidence.chrome_browser.extension_transport_responded, true);
  assert.equal(evidence.chrome_browser.signin_page_rendered, false);
  assert.equal(evidence.google_oauth.account_selection_attempted, false);
  assert.equal(evidence.google_oauth.google_callback_observed, false);
  assert.equal(evidence.google_oauth.application_session_established, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.temporary_browser_tabs_finalized, true);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 29 Google admin-policy boundary retains no account or browser material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_29_google_oauth_admin_policy_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 29);
  assert.equal(evidence.in_app_browser_attempt.new_agent_test_tab_created, true);
  assert.equal(evidence.in_app_browser_attempt.existing_user_tab_claimed, false);
  assert.equal(evidence.in_app_browser_attempt.administrative_policy_verification_available, false);
  assert.equal(evidence.in_app_browser_attempt.signin_page_rendered, false);
  assert.equal(evidence.in_app_browser_attempt.retry_or_browser_switch_used_to_bypass_policy, false);
  assert.equal(evidence.google_oauth.account_selection_attempted, false);
  assert.equal(evidence.google_oauth.google_callback_observed, false);
  assert.equal(evidence.google_oauth.application_session_established, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.temporary_browser_tabs_finalized, true);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 29 S5-T3 gate audit keeps current production proof distinct from historical support", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_29_s5_t3_gate_audit.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 29);
  assert.equal(evidence.frozen_taskpack_binding.task_dag_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.traceability_matrix_sha256.length, 64);
  assert.equal(evidence.gate_assessment.r003_real_authentication.status, "PARTIAL");
  assert.equal(
    evidence.gate_assessment.r003_real_authentication.v28_to_v29_auth_surface_continuity,
    "PASS_SUPPORT_ONLY",
  );
  assert.equal(
    evidence.gate_assessment.r003_real_authentication.current_v29_email_browser_replay,
    "NOT_PROVEN_FRESH_AGENT_TEST_TAB_NAVIGATION_FAILED_BEFORE_SIGNUP_RENDER",
  );
  assert.equal(evidence.gate_assessment.r004_a_b_isolation.current_v29_physical_a_b_replay, "NOT_RUN");
  assert.equal(evidence.gate_assessment.r005_d1_r2_persistence.current_v29_physical_mapping_or_record_object_reconciliation, "NOT_PROVEN");
  assert.equal(evidence.gate_assessment.r009_saved_version_rollback_restore.status, "PASS");
  assert.equal(evidence.gate_assessment.r009_saved_version_rollback_restore.current_v29_rollback_then_restore, "PASS_PRIVATE_VERSION_29_TO_28_TO_29_OWNER_ONLY");
  assert.equal(evidence.gate_assessment.physical_second_device_history.status, "NOT_RUN");
  assert.equal(evidence.result.s5_t3_core_chains_all_pass, false);
  assert.equal(evidence.result.s5_t3_threshold_met, false);
  assert.equal(evidence.scope_and_cleanup.taskpack_source_modified, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 29 rollback and restore rehearsal retains no deployment or user material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_29_rollback_restore_rehearsal.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.approved_sites_version_number, 29);
  assert.equal(evidence.candidate.previous_saved_sites_version_number, 28);
  assert.equal(evidence.execution.private_deploy_previous_version_succeeded, true);
  assert.equal(evidence.execution.private_restore_approved_version_succeeded, true);
  assert.equal(evidence.post_restore_control_plane.latest_saved_version_number, 29);
  assert.equal(evidence.post_restore_control_plane.approved_version_source_matches_expected, true);
  assert.equal(evidence.post_restore_control_plane.external_visitor_count, 0);
  assert.equal(evidence.result.current_v29_rollback_then_restore_proven, true);
  assert.equal(evidence.execution.deployment_identifiers_recorded, false);
  assert.equal(evidence.scope_and_cleanup.runtime_values_read, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 29 post-restore error check retains no worker log material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_29_post_restore_error_log_check.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 29);
  assert.equal(evidence.read_only_query.errors_only, true);
  assert.equal(evidence.read_only_query.since_minutes, 10);
  assert.equal(evidence.read_only_query.worker_error_event_count, 0);
  assert.equal(evidence.read_only_query.raw_log_messages_recorded, false);
  assert.equal(evidence.result.post_restore_narrow_error_only_window_has_visible_p0, false);
  assert.equal(evidence.result.current_v29_production_p0_absence_fully_proven, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 29 storage-mapping boundary retains no physical resource or provider material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_29_storage_mapping_read_only_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 29);
  assert.equal(evidence.sites_control_plane.logical_d1_binding_name_present, true);
  assert.equal(evidence.sites_control_plane.logical_r2_binding_name_present, true);
  assert.equal(evidence.sites_control_plane.physical_d1_identifier_exposed, false);
  assert.equal(evidence.sites_control_plane.physical_r2_identifier_exposed, false);
  assert.equal(evidence.catalogue_probe.wrangler_identity_authenticated, true);
  assert.equal(evidence.catalogue_probe.d1_catalogue_accessible, false);
  assert.equal(evidence.catalogue_probe.r2_catalogue_accessible, false);
  assert.equal(evidence.catalogue_probe.physical_identifiers_recorded, false);
  assert.equal(evidence.result.direct_d1_r2_reconciliation_proven, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("database_id"), false);
  assert.equal(serialized.includes("bucket_name"), false);
  assert.equal(serialized.includes("Bearer "), false);
  assert.equal(serialized.includes("@"), false);
});

test("Version 28 email-password recovery replay retains no temporary credentials", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_28_email_password_reset_completion_replay.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 28);
  assert.equal(evidence.candidate.canonical_product_domain_used, true);
  assert.equal(evidence.candidate.public_audience_changed, false);
  assert.equal(evidence.controlled_email_password_replay.verification_message_received, true);
  assert.equal(evidence.controlled_email_password_replay.new_password_submission_completed, true);
  assert.equal(evidence.controlled_email_password_replay.new_password_signin_reached_workspace, true);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.scope_and_cleanup.temporary_mailbox_deleted, true);
  assert.equal(evidence.scope_and_cleanup.temporary_credentials_cleared_from_test_runtime, true);
  assert.equal(
    evidence.scope_and_cleanup.temporary_browser_tabs_finalized,
    "NOT_CONFIRMED_ADMIN_POLICY_UNAVAILABLE",
  );
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 28 Google replay policy boundary retains no provider or browser material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_28_google_oauth_browser_policy_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 28);
  assert.equal(evidence.candidate.canonical_product_domain_active, true);
  assert.equal(evidence.candidate.public_audience_changed, false);
  assert.equal(evidence.control_plane_presence_only.google_client_id_key_present, true);
  assert.equal(evidence.control_plane_presence_only.google_client_secret_key_present, true);
  assert.equal(evidence.control_plane_presence_only.runtime_values_recorded, false);
  assert.equal(evidence.controlled_browser_replay.target_page_rendered, false);
  assert.equal(evidence.controlled_browser_replay.google_account_selected, false);
  assert.equal(evidence.controlled_browser_replay.google_callback_observed, false);
  assert.equal(evidence.controlled_browser_replay.application_session_established, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.blank_browser_tab_finalized, true);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 29 auth-surface continuity keeps source support distinct from current browser E2E", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_29_auth_surface_continuity.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.current_sites_version_number, 29);
  assert.equal(evidence.source_continuity.auth_surface_identical_within_declared_scope, true);
  assert.deepEqual(evidence.source_continuity.auth_surface_changed_paths, []);
  assert.equal(evidence.source_continuity.package_dependencies_identical, true);
  assert.equal(evidence.source_continuity.package_dev_dependencies_identical, true);
  assert.equal(evidence.current_local_auth_contract.status, "PASS_LOCAL_CONTRACT");
  assert.equal(evidence.current_local_auth_contract.test_count, 19);
  assert.equal(evidence.current_local_auth_contract.passed, 19);
  assert.equal(evidence.controlled_prior_browser_e2e.version, 28);
  assert.equal(
    evidence.controlled_prior_browser_e2e.forgot_password_reset_delivery_new_password_signin_completed,
    true,
  );
  assert.equal(evidence.current_v29_browser_e2e.email_registration_verification_reset_signin_replayed, "NOT_RUN");
  assert.equal(
    evidence.current_v29_browser_e2e.google_callback_and_session,
    "NOT_PROVEN_ADMINISTRATIVE_POLICY_VERIFICATION_UNAVAILABLE_BEFORE_SIGNIN_RENDER",
  );
  assert.equal(evidence.result.current_v29_real_email_browser_e2e_proven, false);
  assert.equal(evidence.result.current_v29_google_callback_and_session_proven, false);
  assert.equal(evidence.result.s5_t3_authentication_gate_satisfied, false);
  assert.equal(evidence.scope_and_cleanup.browser_or_mailbox_used_in_this_increment, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 29 email browser boundary retains no mailbox, account, or navigation material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_29_email_browser_navigation_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 29);
  assert.equal(evidence.controlled_browser_attempt.fresh_agent_test_tab_created, true);
  assert.equal(evidence.controlled_browser_attempt.target_route, "/auth/sign-up");
  assert.equal(evidence.controlled_browser_attempt.navigation_completed, false);
  assert.equal(evidence.controlled_browser_attempt.signup_page_rendered, false);
  assert.equal(evidence.controlled_browser_attempt.navigation_failure_cause_determined, false);
  assert.equal(evidence.controlled_browser_attempt.retry_or_browser_switch_used_to_bypass_boundary, false);
  assert.equal(evidence.controlled_browser_attempt.bypass_token_generated_or_used, false);
  assert.equal(evidence.controlled_browser_attempt.account_or_email_entered, false);
  assert.equal(evidence.controlled_browser_attempt.credential_entered, false);
  assert.equal(evidence.scope_and_cleanup.mailbox_content_or_identity_recorded, false);
  assert.equal(evidence.scope_and_cleanup.mailbox_search_or_read_in_this_increment, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.temporary_test_tab_finalized, true);
  assert.equal(evidence.scope_and_cleanup.temporary_application_account_created, false);
  assert.equal(evidence.result.current_v29_email_registration_verification_reset_signin_proven, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});
