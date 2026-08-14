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

test("Version 33 S5-T1 saved candidate evidence preserves the private boundary", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_33_s5_t1_saved_candidate.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S5-T1");
  assert.equal(evidence.phase, "S5_T1_PRIVATE_SAVED_VERSION");
  assert.equal(evidence.status, "PASS_PRIVATE_SAVED_VERSION_CANDIDATE");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.candidate.saved_version_number, 33);
  assert.equal(evidence.candidate.source_readback_matches_pushed_candidate, true);
  assert.equal(evidence.candidate.archive_stored_by_sites, true);
  assert.equal(evidence.private_access.site_active, true);
  assert.equal(evidence.private_access.current_user_role, "owner");
  assert.equal(evidence.private_access.access_mode, "custom");
  assert.equal(evidence.private_access.allowed_user_count, 1);
  assert.equal(evidence.private_access.allowed_group_count, 0);
  assert.equal(evidence.private_access.external_visitor_count, 0);
  assert.equal(evidence.scope_and_limits.deployment_action_called, false);
  assert.equal(evidence.scope_and_limits.public_audience_changed, false);
  assert.equal(evidence.scope_and_limits.github_uploaded, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 34 S5-T1 saved candidate preserves reviewed-source and private boundaries", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_34_s5_t1_saved_candidate.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S5-T1");
  assert.equal(evidence.phase, "S5_T1_PRIVATE_SAVED_VERSION");
  assert.equal(evidence.status, "PASS_PRIVATE_SAVED_VERSION_CANDIDATE");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.candidate.saved_version_number, 34);
  assert.equal(evidence.candidate.source_readback_matches_pushed_candidate, true);
  assert.equal(evidence.candidate.archive_stored_by_sites, true);
  assert.equal(evidence.source_identity.approved_local_commit.length, 40);
  assert.equal(evidence.source_identity.approved_local_project_tree.length, 40);
  assert.equal(evidence.source_identity.sites_projection_commit.length, 40);
  assert.equal(evidence.source_identity.projection_tree_matches_approved_local_project_tree, true);
  assert.equal(evidence.source_identity.push_mode, "NON_FORCE_FAST_FORWARD");
  assert.equal(evidence.build_archive.status, "PASS_EXACT_SOURCE_BUILD_AND_PACKAGE");
  assert.equal(evidence.build_archive.built_in_isolated_candidate_copy, true);
  assert.equal(evidence.build_archive.local_checks.npm_run_tenant, "PASS");
  assert.equal(evidence.build_archive.local_checks.npm_run_workbench_data, "PASS");
  assert.equal(evidence.private_access.site_active, true);
  assert.equal(evidence.private_access.current_user_role, "owner");
  assert.equal(evidence.private_access.access_mode, "custom");
  assert.equal(evidence.private_access.allowed_user_count, 1);
  assert.equal(evidence.private_access.allowed_group_count, 0);
  assert.equal(evidence.private_access.external_visitor_count, 0);
  assert.equal(evidence.sites_saved_version.source_readback_matches_projection, true);
  assert.equal(evidence.sites_saved_version.archive_storage_present, true);
  assert.equal(evidence.sites_saved_version.new_candidate_deployed, false);
  assert.equal(evidence.scope_and_limits.deployment_action_called, false);
  assert.equal(evidence.scope_and_limits.runtime_values_read_or_changed, false);
  assert.equal(evidence.scope_and_limits.public_audience_changed, false);
  assert.equal(evidence.scope_and_limits.github_uploaded, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 35 S5-T1 archival evidence preserves the reviewed session-scope recovery source", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_35_s5_t1_saved_candidate.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S5-T1");
  assert.equal(evidence.phase, "S5_T1_PRIVATE_SAVED_VERSION");
  assert.equal(evidence.status, "PASS_PRIVATE_SAVED_VERSION_CANDIDATE");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.candidate.saved_version_number, 35);
  assert.equal(evidence.candidate.source_pushed_to_sites_dedicated_channel, true);
  assert.equal(evidence.candidate.source_readback_matches_pushed_candidate, true);
  assert.equal(evidence.candidate.archive_stored_by_sites, true);
  assert.equal(evidence.source_identity.approved_local_commit.length, 40);
  assert.equal(evidence.source_identity.approved_local_project_tree.length, 40);
  assert.equal(evidence.source_identity.content_projection_parent, null);
  assert.equal(evidence.source_identity.all_projection_trees_match_approved_local_project_tree, true);
  assert.equal(evidence.source_identity.push_mode, "NON_FORCE_FAST_FORWARD");
  assert.equal(evidence.source_identity.sites_source_branch_readback_matches_source_channel_commit, true);
  assert.equal(evidence.build_archive.status, "PASS_EXACT_SOURCE_BUILD_AND_PACKAGE");
  assert.equal(evidence.build_archive.built_in_isolated_candidate_copy, true);
  assert.equal(evidence.build_archive.local_checks.npm_run_verify_source_projection, "PASS_SOURCE_PROJECTION_CONTRACT");
  assert.equal(evidence.private_access.site_active, true);
  assert.equal(evidence.private_access.current_user_role, "owner");
  assert.equal(evidence.private_access.access_mode, "custom");
  assert.equal(evidence.private_access.allowed_user_count, 1);
  assert.equal(evidence.private_access.allowed_group_count, 0);
  assert.equal(evidence.private_access.external_visitor_count, 0);
  assert.equal(evidence.sites_saved_version.version_number, 35);
  assert.equal(evidence.sites_saved_version.source_readback_matches_source_channel_commit, true);
  assert.equal(evidence.sites_saved_version.archive_storage_present, true);
  assert.equal(evidence.sites_saved_version.new_candidate_deployed, false);
  assert.equal(evidence.scope_and_limits.deployment_action_called, false);
  assert.equal(evidence.scope_and_limits.runtime_values_read_or_changed, false);
  assert.equal(evidence.scope_and_limits.public_audience_changed, false);
  assert.equal(evidence.scope_and_limits.github_uploaded, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 37 S5-T1 saved candidate remains a source-bound, undeployed historical record", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_37_s5_t1_saved_candidate.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S5-T1");
  assert.equal(evidence.status, "PASS_PRIVATE_SAVED_VERSION_CANDIDATE");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.candidate.saved_version_number, 37);
  assert.equal(evidence.candidate.source_pushed_to_sites_dedicated_channel, true);
  assert.equal(evidence.candidate.source_readback_matches_pushed_candidate, true);
  assert.equal(evidence.source_identity.current_local_candidate_commit_bound, true);
  assert.equal(evidence.source_identity.project_tree_matches_sites_source_channel, true);
  assert.equal(evidence.source_identity.sites_source_branch_readback_matches_candidate, true);
  assert.equal(evidence.source_identity.push_mode, "NON_FORCE_FAST_FORWARD");
  assert.equal(evidence.source_identity.raw_commit_identifiers_recorded, false);
  assert.equal(evidence.build_archive.status, "PASS_EXACT_SOURCE_BUILD_AND_PACKAGE");
  assert.equal(evidence.build_archive.required_entries_present.server_entry, true);
  assert.equal(evidence.build_archive.required_entries_present.hosting_metadata, true);
  assert.equal(evidence.build_archive.required_entries_present.database_migrations, true);
  assert.equal(evidence.site_access_snapshot.access_mode, "public");
  assert.equal(evidence.site_access_snapshot.access_policy_changed, false);
  assert.equal(evidence.site_access_snapshot.public_audience_changed, false);
  assert.equal(evidence.sites_saved_version.new_candidate_deployed, false);
  assert.equal(evidence.post_save_readback.candidate_deployed, false);
  assert.equal(evidence.post_save_readback.deployment_action_called, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 38 S5-T1 current saved candidate is source-bound, archived, and undeployed", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_38_s5_t1_saved_candidate.json", import.meta.url),
      "utf8",
    ),
  );
  const current = JSON.parse(
    await readFile(new URL("../13_evidence/saved_version.json", import.meta.url), "utf8"),
  );
  const serialized = JSON.stringify({ evidence, current });

  assert.equal(evidence.task_id, "S5-T1");
  assert.equal(evidence.status, "PASS_PRIVATE_SAVED_VERSION_CANDIDATE");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.candidate.s4_t3a_readiness, "READINESS_PASS");
  assert.equal(evidence.candidate.saved_version_number, 38);
  assert.equal(evidence.candidate.source_pushed_to_sites_dedicated_channel, true);
  assert.equal(evidence.candidate.source_readback_matches_pushed_candidate, true);
  assert.equal(evidence.source_identity.current_local_candidate_commit_bound, true);
  assert.equal(evidence.source_identity.project_tree_matches_sites_source_channel, true);
  assert.equal(evidence.source_identity.sites_source_branch_readback_matches_candidate, true);
  assert.equal(evidence.source_identity.push_mode, "NON_FORCE_FAST_FORWARD");
  assert.equal(evidence.source_identity.source_credential_persisted, false);
  assert.equal(evidence.sites_saved_version.archive_storage_present, true);
  assert.equal(evidence.sites_saved_version.new_candidate_deployed, false);
  assert.equal(evidence.post_save_readback.candidate_deployed, false);
  assert.equal(evidence.post_save_readback.deployment_action_called, false);
  assert.equal(current.sites_saved_version.version_number, 38);
  assert.equal(current.sites_saved_version.source_readback_matches_pushed_candidate, true);
  assert.equal(current.post_save_readback.candidate_deployed, false);
  assert.equal(current.post_save_readback.access_policy_changed, false);
  assert.equal(current.post_save_readback.access_policy_rechecked, false);
  assert.equal(current.candidate_exposure_boundary.saved_candidate_is_undeployed, true);
  assert.equal(current.candidate_exposure_boundary.existing_live_url_is_not_runtime_evidence_for_version_38, true);
  assert.equal(current.sensitive_values_recorded, false);
  assert.equal(current.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 37 S5-T2 configuration evidence is value-free and preserves public access", async () => {
  const configuration = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_37_s5_t2_runtime_configuration.json", import.meta.url),
      "utf8",
    ),
  );
  const boundary = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_37_s5_t2_local_shell_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify({ configuration, boundary });

  assert.equal(configuration.task_id, "S5-T2");
  assert.equal(configuration.status, "PASS_SAVED_CANDIDATE_RUNTIME_CONFIGURATION_PRESENCE_ONLY");
  assert.equal(configuration.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(configuration.candidate.saved_version_number, 37);
  assert.equal(configuration.candidate.source_readback_present, true);
  assert.equal(configuration.candidate.source_readback_matches_saved_candidate, true);
  assert.equal(configuration.candidate.archive_readback_present, true);
  assert.equal(configuration.candidate.configuration_revision_unchanged_from_prior_evidence, true);
  assert.equal(configuration.configuration_presence.revision, 8);
  assert.equal(configuration.configuration_presence.entry_count, 15);
  assert.equal(configuration.configuration_presence.secret_entry_count, 11);
  assert.equal(configuration.configuration_presence.non_secret_entry_count, 4);
  assert.equal(configuration.configuration_presence.required_auth_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_email_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_privacy_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_abuse_protection_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_origin_key_type_present, true);
  assert.equal(configuration.configuration_presence.configuration_values_inspected, false);
  assert.equal(configuration.configuration_presence.configuration_values_recorded, false);
  assert.equal(configuration.site_access_snapshot.site_active, true);
  assert.equal(configuration.site_access_snapshot.current_user_role, "owner");
  assert.equal(configuration.site_access_snapshot.access_mode, "public");
  assert.equal(configuration.site_access_snapshot.access_scope_preserved, true);
  assert.equal(configuration.site_access_snapshot.v37_deployment_action_called, false);
  assert.equal(configuration.owner_gate_support.asset_authorization, "PASS_FINAL_AUTHORIZED_ASSETS");
  assert.equal(configuration.owner_gate_support.asset_contract_tests, "PASS_2_OF_2");
  assert.equal(configuration.owner_gate_support.privacy_contract_tests, "PASS_3_OF_3");
  assert.equal(configuration.owner_gate_support.owner_activation_evidence_redaction_tests, "PASS_4_OF_4");
  assert.equal(configuration.scope_and_limits.deployment_action_called, false);
  assert.equal(configuration.scope_and_limits.public_audience_changed, false);
  assert.equal(configuration.scope_and_limits.github_uploaded, false);
  assert.equal(boundary.status, "EXPECTED_NONPASS_EMPTY_LOCAL_SHELL");
  assert.equal(boundary.execution.empty_shell_nonpass_expected, true);
  assert.equal(boundary.execution.hosted_configuration_missing_inferred, false);
  assert.equal(boundary.execution.protected_runtime_values_injected_into_local_shell, false);
  assert.equal(boundary.execution.command_output_retained, false);
  assert.equal(boundary.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 38 S5-T2 configuration evidence is value-free and keeps the local-shell boundary separate", async () => {
  const configuration = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_38_s5_t2_runtime_configuration.json", import.meta.url),
      "utf8",
    ),
  );
  const boundary = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_38_s5_t2_local_shell_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify({ configuration, boundary });

  assert.equal(configuration.task_id, "S5-T2");
  assert.equal(configuration.status, "PASS_SAVED_CANDIDATE_RUNTIME_CONFIGURATION_PRESENCE_ONLY");
  assert.equal(configuration.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(configuration.candidate.saved_version_number, 38);
  assert.equal(configuration.candidate.source_readback_present, true);
  assert.equal(configuration.candidate.source_readback_matches_saved_candidate, true);
  assert.equal(configuration.candidate.archive_readback_present, true);
  assert.equal(configuration.candidate.latest_saved_version_matches_candidate, true);
  assert.equal(configuration.candidate.configuration_revision_unchanged_from_prior_evidence, true);
  assert.equal(configuration.configuration_presence.revision, 8);
  assert.equal(configuration.configuration_presence.entry_count, 15);
  assert.equal(configuration.configuration_presence.secret_entry_count, 11);
  assert.equal(configuration.configuration_presence.non_secret_entry_count, 4);
  assert.equal(configuration.configuration_presence.required_auth_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_email_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_privacy_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_abuse_protection_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_origin_key_type_present, true);
  assert.equal(configuration.configuration_presence.configuration_values_inspected, false);
  assert.equal(configuration.configuration_presence.configuration_values_recorded, false);
  assert.equal(configuration.site_access_boundary.access_policy_rechecked, false);
  assert.equal(configuration.site_access_boundary.access_policy_changed, false);
  assert.equal(configuration.owner_gate_support.asset_authorization, "PASS_FINAL_AUTHORIZED_ASSETS");
  assert.equal(configuration.owner_gate_support.asset_contract_tests, "PASS_2_OF_2");
  assert.equal(configuration.owner_gate_support.privacy_contract_tests, "PASS_3_OF_3");
  assert.equal(configuration.owner_gate_support.owner_activation_evidence_redaction_tests, "PASS_4_OF_4");
  assert.equal(configuration.scope_and_limits.deployment_action_called, false);
  assert.equal(configuration.scope_and_limits.public_audience_changed, false);
  assert.equal(configuration.scope_and_limits.github_uploaded, false);
  assert.equal(boundary.status, "EXPECTED_NONPASS_EMPTY_LOCAL_SHELL");
  assert.equal(boundary.execution.empty_shell_nonpass_expected, true);
  assert.equal(boundary.execution.hosted_configuration_missing_inferred, false);
  assert.equal(boundary.execution.protected_runtime_values_injected_into_local_shell, false);
  assert.equal(boundary.execution.command_output_retained, false);
  assert.equal(boundary.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 38 S5-T3 public-entry and operations prechecks retain their controlled boundaries", async () => {
  const publicEntry = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_38_s5_t3_public_entry_precheck.json", import.meta.url),
      "utf8",
    ),
  );
  const ops = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_38_s5_t3_ops_projection_precheck.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify({ publicEntry, ops });

  assert.equal(publicEntry.task_id, "S5-T3");
  assert.equal(publicEntry.status, "BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK");
  assert.equal(publicEntry.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(publicEntry.candidate.saved_version_number, 38);
  assert.equal(publicEntry.candidate.candidate_deployed, false);
  assert.equal(publicEntry.candidate.public_runtime_version_bound_to_v38, false);
  assert.equal(publicEntry.unauthenticated_public_entry.root_http_200, true);
  assert.equal(publicEntry.unauthenticated_public_entry.sign_in_http_200, true);
  assert.equal(publicEntry.unauthenticated_public_entry.sign_up_http_200, true);
  assert.equal(publicEntry.unauthenticated_public_entry.forgot_password_http_200, true);
  assert.equal(publicEntry.unauthenticated_public_entry.verify_email_http_200, true);
  assert.equal(publicEntry.unauthenticated_public_entry.public_configuration_http_200, true);
  assert.equal(publicEntry.unauthenticated_public_entry.unauthenticated_profile_http_401, true);
  assert.equal(publicEntry.real_flow_boundary.email_or_password_submitted, false);
  assert.equal(publicEntry.real_flow_boundary.turnstile_response_submitted, false);
  assert.equal(publicEntry.real_flow_boundary.google_account_selected, false);
  assert.equal(publicEntry.real_flow_boundary.browser_cookie_or_storage_inspected, false);
  assert.equal(publicEntry.real_flow_boundary.real_authentication_replay, "NOT_RUN_NO_CONTROLLED_TEST_IDENTITIES");
  assert.equal(publicEntry.scope_and_limits.deployment_action_called, false);
  assert.equal(publicEntry.scope_and_limits.github_uploaded, false);
  assert.equal(ops.task_id, "S5-T3");
  assert.equal(ops.status, "BLOCKED_LOCAL_OPS_PROJECTION");
  assert.equal(ops.static_safety_guards.audit_schema_guard, true);
  assert.equal(ops.static_safety_guards.security_audit_events_schema_present, true);
  assert.equal(ops.static_safety_guards.file_object_prefix_isolation_guard, true);
  assert.equal(ops.unauthenticated_adapter_boundary.ops_token_injected, false);
  assert.equal(ops.unauthenticated_adapter_boundary.status_adapter_http_503, true);
  assert.equal(ops.unauthenticated_adapter_boundary.ovh_adapter_http_503, true);
  assert.equal(ops.unauthenticated_adapter_boundary.private_database_adapter_http_503, true);
  assert.equal(ops.unauthenticated_adapter_boundary.adapter_response_bodies_retained, false);
  assert.equal(ops.scope_and_limits.deployment_action_called, false);
  assert.equal(ops.scope_and_limits.github_uploaded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 35 S5-T2 configuration evidence preserves value-free private continuity", async () => {
  const configuration = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_35_s5_t2_runtime_configuration.json", import.meta.url),
      "utf8",
    ),
  );
  const boundary = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_35_s5_t2_local_shell_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify({ configuration, boundary });

  assert.equal(configuration.task_id, "S5-T2");
  assert.equal(configuration.status, "PASS_PRIVATE_RUNTIME_CONFIGURATION_PRESENCE_ONLY");
  assert.equal(configuration.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(configuration.candidate.saved_version_number, 35);
  assert.equal(configuration.candidate.source_readback_present, true);
  assert.equal(configuration.candidate.source_readback_matches_saved_candidate, true);
  assert.equal(configuration.candidate.archive_readback_present, true);
  assert.equal(configuration.candidate.configuration_revision_unchanged_from_prior_private_configuration_evidence, true);
  assert.equal(configuration.configuration_presence.revision, 8);
  assert.equal(configuration.configuration_presence.entry_count, 15);
  assert.equal(configuration.configuration_presence.secret_entry_count, 11);
  assert.equal(configuration.configuration_presence.non_secret_entry_count, 4);
  assert.equal(configuration.configuration_presence.required_auth_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_email_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_privacy_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_abuse_protection_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_origin_key_type_present, true);
  assert.equal(configuration.configuration_presence.configuration_values_inspected, false);
  assert.equal(configuration.configuration_presence.configuration_values_recorded, false);
  assert.equal(configuration.private_site_state.site_active, true);
  assert.equal(configuration.private_site_state.current_user_role, "owner");
  assert.equal(configuration.private_site_state.access_mode, "custom");
  assert.equal(configuration.private_site_state.allowed_users_count, 1);
  assert.equal(configuration.private_site_state.allowed_groups_count, 0);
  assert.equal(configuration.private_site_state.external_visitor_count, 0);
  assert.equal(configuration.private_site_state.latest_version_matches_saved_candidate, true);
  assert.equal(configuration.private_site_state.v35_deployment_action_called, false);
  assert.equal(configuration.owner_gate_support.asset_authorization, "PASS_FINAL_AUTHORIZED_ASSETS");
  assert.equal(configuration.owner_gate_support.asset_contract_tests, "PASS_2_OF_2");
  assert.equal(configuration.owner_gate_support.privacy_contract_tests, "PASS_3_OF_3");
  assert.equal(configuration.owner_gate_support.owner_activation_evidence_redaction_tests, "PASS_4_OF_4");
  assert.equal(configuration.scope_and_limits.deployment_action_called, false);
  assert.equal(configuration.scope_and_limits.public_audience_changed, false);
  assert.equal(configuration.scope_and_limits.github_uploaded, false);
  assert.equal(boundary.status, "NOT_HOSTED_CONFIGURATION_TEST");
  assert.equal(boundary.execution.empty_shell_nonpass_expected, true);
  assert.equal(boundary.execution.hosted_configuration_missing_inferred, false);
  assert.equal(boundary.execution.protected_runtime_values_injected_into_local_shell, false);
  assert.equal(boundary.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 35 S5-T3 private deployment and rollback evidence does not overclaim browser E2E", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_35_s5_t3_controlled_private_deployment_and_rollback.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S5-T3");
  assert.equal(evidence.status, "PASS_CONTROLLED_PRIVATE_DEPLOY_AND_ROLLBACK_PARTIAL");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.candidate.saved_version_number, 35);
  assert.equal(evidence.candidate.source_readback_matches_saved_candidate, true);
  assert.equal(evidence.candidate.archive_stored_by_sites, true);
  assert.equal(evidence.private_access.site_active, true);
  assert.equal(evidence.private_access.current_user_role, "owner");
  assert.equal(evidence.private_access.access_mode, "custom");
  assert.equal(evidence.private_access.allowed_user_count, 1);
  assert.equal(evidence.private_access.allowed_group_count, 0);
  assert.equal(evidence.private_access.external_visitor_count, 0);
  assert.equal(evidence.controlled_private_deployment.deployed_version_number, 35);
  assert.equal(evidence.controlled_private_deployment.terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.rollback_version_number, 34);
  assert.equal(evidence.rollback_and_restore.rollback_terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.restore_version_number, 35);
  assert.equal(evidence.rollback_and_restore.restore_terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.private_access_preserved_after_rollback_and_restore, true);
  assert.equal(evidence.post_restore_observation.error_event_count, 0);
  assert.equal(evidence.post_restore_observation.log_bodies_retained, false);
  assert.equal(evidence.controlled_browser_e2e.browser_control_runtime_available, false);
  assert.equal(evidence.controlled_browser_e2e.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.controlled_browser_e2e.sites_bypass_token_generated_or_used, false);
  assert.equal(
    evidence.controlled_browser_e2e.email_registration_verification_reset_and_signin,
    "NOT_RUN_NO_CONTROLLED_BROWSER_EXECUTOR",
  );
  assert.equal(
    evidence.controlled_browser_e2e.a_b_tenant_isolation_and_second_device_history,
    "NOT_RUN_NO_CONTROLLED_BROWSER_EXECUTOR",
  );
  assert.equal(
    evidence.controlled_browser_e2e.d1_r2_reconciliation,
    "NOT_PROVEN_SITES_TARGET_NOT_RESOLVED_THROUGH_AUTHORIZED_WORKERS_CATALOGUE",
  );
  assert.equal(evidence.cloudflare_storage_catalogue_boundary.authenticated, true);
  assert.equal(evidence.cloudflare_storage_catalogue_boundary.configuration_values_read_or_logged, false);
  assert.equal(evidence.cloudflare_storage_catalogue_boundary.resource_catalogues_read, true);
  assert.equal(evidence.cloudflare_storage_catalogue_boundary.resource_names_or_identifiers_recorded, false);
  assert.equal(evidence.scope_and_limits.public_audience_changed, false);
  assert.equal(evidence.scope_and_limits.github_uploaded, false);
  assert.equal(evidence.scope_and_limits.product_pass_claimed, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 37 public deployment and recovery evidence retains the current limits", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/version_37_s5_t3_public_deployment_and_recovery.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S5-T3");
  assert.equal(evidence.status, "PASS_PUBLIC_DEPLOY_AND_RECOVERY_PARTIAL");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.candidate.saved_version_number, 37);
  assert.equal(evidence.candidate.source_readback_matches_saved_candidate, true);
  assert.equal(evidence.candidate.archive_stored_by_sites, true);
  assert.equal(evidence.public_access_snapshot.access_mode, "public");
  assert.equal(evidence.public_access_snapshot.public_audience_changed_in_this_phase, false);
  assert.equal(evidence.public_deployment.deployed_version_number, 37);
  assert.equal(evidence.public_deployment.terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.rollback_version_number, 36);
  assert.equal(evidence.rollback_and_restore.rollback_terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.restore_version_number, 37);
  assert.equal(evidence.rollback_and_restore.restore_terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.public_access_preserved_after_rollback_and_restore, true);
  assert.equal(evidence.post_restore_public_smoke.root_http_200, true);
  assert.equal(evidence.post_restore_public_smoke.unauthenticated_profile_http_401, true);
  assert.equal(evidence.post_restore_public_smoke.primary_menu_checked_view_count, 9);
  assert.equal(evidence.post_restore_public_smoke.primary_menu_all_http_200, true);
  assert.equal(evidence.post_restore_public_smoke.primary_menu_distinct_render_count, 9);
  assert.equal(evidence.post_restore_public_smoke.primary_menu_raw_html_retained, false);
  assert.equal(evidence.post_restore_public_smoke.google_authorization_host_is_google, true);
  assert.equal(evidence.post_restore_public_smoke.google_callback_origin_matches_public_origin, true);
  assert.equal(evidence.post_restore_public_smoke.google_callback_path_matches_expected, true);
  assert.equal(evidence.post_restore_public_smoke.google_redirect_followed, false);
  assert.equal(evidence.post_restore_observation.error_event_count, 0);
  assert.equal(evidence.post_restore_observation.log_bodies_retained, false);
  assert.equal(evidence.continued_anonymous_auth_boundary.site_active_and_public_reconfirmed, true);
  assert.equal(evidence.continued_anonymous_auth_boundary.current_saved_version_number, 37);
  assert.equal(evidence.continued_anonymous_auth_boundary.email_auth_views_checked_count, 4);
  assert.equal(evidence.continued_anonymous_auth_boundary.email_auth_views_all_http_200, true);
  assert.equal(evidence.continued_anonymous_auth_boundary.email_auth_views_expected_markers_present, true);
  assert.equal(evidence.continued_anonymous_auth_boundary.sign_in_and_sign_up_csp_allows_turnstile_script, true);
  assert.equal(evidence.continued_anonymous_auth_boundary.sign_in_and_sign_up_csp_allows_same_origin_connect, true);
  assert.equal(evidence.continued_anonymous_auth_boundary.empty_noncredential_auth_requests_checked_count, 5);
  assert.equal(evidence.continued_anonymous_auth_boundary.empty_noncredential_auth_requests_all_http_400, true);
  assert.equal(evidence.continued_anonymous_auth_boundary.empty_noncredential_auth_requests_any_server_5xx, false);
  assert.equal(evidence.continued_anonymous_auth_boundary.requests_contained_email_password_or_captcha, false);
  assert.equal(evidence.continued_anonymous_auth_boundary.fresh_unauthenticated_profile_http_401, true);
  assert.equal(evidence.continued_anonymous_auth_boundary.response_cookie_values_retained, false);
  assert.equal(evidence.continued_anonymous_auth_boundary.error_only_log_events_checked, 6);
  assert.equal(evidence.continued_anonymous_auth_boundary.error_only_log_events_all_match_this_unauthenticated_probe, true);
  assert.equal(evidence.continued_anonymous_auth_boundary.unexpected_runtime_error_observed, false);
  assert.equal(evidence.controlled_browser_e2e.browser_control_runtime_available, false);
  assert.equal(evidence.controlled_browser_e2e.sites_bypass_token_generated_or_used, false);
  assert.equal(evidence.scope_and_limits.github_uploaded, false);
  assert.equal(evidence.scope_and_limits.product_pass_claimed, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("production ledger identifies Version 126 as the current public-entry partial evidence", async () => {
  const ledger = JSON.parse(
    await readFile(new URL("../13_evidence/production.json", import.meta.url), "utf8"),
  );

  assert.equal(ledger.status, "PUBLIC_ENTRY_VERSION_126_S5_T3_PARTIAL");
  assert.equal(ledger.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(ledger.current_version_126_habit_feedback.status, "PASS_PUBLIC_VERSION_126_GUEST_HABIT_FEEDBACK");
  assert.equal(ledger.current_version_126_habit_feedback.current_saved_version_number, 126);
  assert.equal(ledger.current_version_126_habit_feedback.previous_saved_version_number, 125);
  assert.equal(ledger.current_version_126_habit_feedback.guest_habit_click, "EARLY_CHECKIN_IMMEDIATE_FEEDBACK_AND_REFRESH_READBACK_PASSED");
  assert.equal(ledger.current_version_126_habit_feedback.runtime_exceptions, 0);
  assert.equal(ledger.current_version_126_habit_feedback.google_identity_entry, "PUBLIC_SIGN_IN_BUTTON_READY_WITH_CONFIGURED_CLIENT_AND_ZERO_RUNTIME_EXCEPTIONS");
  assert.equal(ledger.current_version_126_habit_feedback.guest_control_matrix, "PASS_9_MENU_ROUTES_18_AUDITED_CONTROLS_WITH_REFRESH_READBACK");
  assert.equal(ledger.current_version_125_rollback_restore.status, "PASS_PUBLIC_VERSION_125_ROLLBACK_RESTORE");
  assert.equal(ledger.current_version_125_rollback_restore.current_saved_version_number, 125);
  assert.equal(ledger.current_version_125_rollback_restore.rollback_target_saved_version_number, 124);
  assert.equal(ledger.current_version_125_rollback_restore.rollback_restore, "V125_TO_V124_TO_V125_SUCCEEDED");
  assert.equal(ledger.current_public_candidate.saved_version_number, 126);
  assert.equal(ledger.current_public_candidate.source_recorded_by_sites, true);
  assert.equal(ledger.current_public_candidate.archive_stored_by_sites, true);
  assert.equal(ledger.current_public_candidate.public_deployment, "SUCCEEDED");
  assert.equal(ledger.current_public_candidate.previous_saved_version_number, 125);
  assert.equal(ledger.current_public_candidate.rollback_rehearsal_for_current_version, "NOT_RUN_PREVIOUS_V125_TO_V124_TO_V125_REHEARSAL_RETAINS_A_SAVED_RECOVERY_POINT");
  assert.equal(ledger.current_public_candidate.guest_habit_feedback_replay, "PASS_IMMEDIATE_VISIBLE_STATE_THEN_REFRESH_READBACK");
  assert.equal(ledger.current_public_candidate.guest_habit_feedback_runtime_exceptions, 0);
  assert.equal(ledger.current_public_candidate.google_identity_entry_readiness, "PASS_PUBLIC_SIGN_IN_BUTTON_READY_WITH_CONFIGURED_CLIENT");
  assert.equal(ledger.current_public_candidate.guest_control_matrix, "PASS_9_MENU_ROUTES_18_AUDITED_CONTROLS_WITH_REFRESH_READBACK");
  assert.equal(ledger.observed_interface.current_version_126_guest_control_matrix, "PASS_9_MENU_ROUTES_18_AUDITED_CONTROLS_WITH_REFRESH_READBACK_RUNTIME_EXCEPTIONS_0");
  assert.equal(ledger.current_public_candidate.authenticated_product_flow_current_version, "NOT_RUN_NO_COMPLETED_CONTROLLED_ACCOUNT_REPLAY");
  assert.equal(ledger.current_private_candidate.saved_version_number, 35);
  assert.equal(ledger.current_private_candidate.source_readback_matches_saved_candidate, true);
  assert.equal(ledger.current_private_candidate.archive_stored_by_sites, true);
  assert.equal(ledger.current_private_candidate.controlled_private_deployment, "SUCCEEDED");
  assert.equal(ledger.current_private_candidate.rollback_restore, "V35_TO_V34_TO_V35_SUCCEEDED");
  assert.equal(
    ledger.current_private_candidate.storage_binding_reconciliation,
    "NOT_PROVEN_SITES_TARGET_NOT_RESOLVED_THROUGH_AUTHORIZED_WORKERS_CATALOGUE",
  );
  assert.equal(ledger.current_private_candidate.public_audience_changed, false);
  assert.equal(ledger.current_private_candidate.browser_e2e_current_version, "NOT_RUN_NO_CONTROLLED_BROWSER_EXECUTOR");
  assert.equal(ledger.private_deployment_access_snapshot.access_mode, "custom");
  assert.equal(ledger.current_public_access.access_mode, "public");
  assert.equal(ledger.current_public_access.anonymous_entry_probe.root, "HTTP_200");
  assert.equal(ledger.current_public_access.anonymous_entry_probe.sign_up, "HTTP_200");
  assert.equal(ledger.current_public_access.anonymous_entry_probe.unauthenticated_profile, "HTTP_401");
  assert.equal(ledger.current_public_access.auth_runtime_public_readiness.turnstile_site_key_present, true);
  assert.equal(ledger.current_public_access.google_oauth_initiation.status, "HTTP_200_GOOGLE_AUTHORIZATION_URL_RETURNED");
  assert.equal(ledger.current_public_access.google_oauth_initiation.authorization_host_is_google, true);
  assert.equal(ledger.current_public_access.google_oauth_initiation.redirect_uri_matches_public_origin, true);
  assert.equal(ledger.current_public_access.google_oauth_initiation.state_present, true);
  assert.equal(ledger.current_public_access.google_oauth_initiation.redirect_followed, false);
  assert.equal(ledger.current_public_access.google_oauth_initiation.provider_callback_or_application_session_proven, false);
  assert.equal(ledger.current_public_access.public_sign_up_surface.status, "HTTP_200");
  assert.equal(ledger.current_public_access.public_sign_up_surface.turnstile_mount_present, true);
  assert.equal(ledger.current_public_access.primary_menu_rendering.checked_view_count, 9);
  assert.equal(ledger.current_public_access.primary_menu_rendering.version_number, 37);
  assert.equal(ledger.current_public_access.primary_menu_rendering.distinct_render_count, 9);
  assert.equal(ledger.controlled_deployment_and_recovery.version_35_private_deploy, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.version_35_to_34_private_rollback, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.version_34_to_35_private_restore, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.live_version_matches_version_35, false);
  assert.equal(ledger.controlled_deployment_and_recovery.version_36_public_deploy, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.version_126_public_deploy, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.version_125_public_deploy, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.version_125_to_124_public_rollback, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.version_124_to_125_public_restore, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.version_37_public_deploy, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.version_37_to_36_public_rollback, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.version_36_to_37_public_restore, "SUCCEEDED");
  assert.equal(ledger.controlled_deployment_and_recovery.live_version_matches_version_36, false);
  assert.equal(ledger.controlled_deployment_and_recovery.live_version_matches_version_37, false);
  assert.equal(ledger.controlled_deployment_and_recovery.live_version_matches_version_124, false);
  assert.equal(ledger.controlled_deployment_and_recovery.live_version_matches_version_125, false);
  assert.equal(ledger.controlled_deployment_and_recovery.live_version_matches_version_126, true);
  assert.equal(
    ledger.evidence_files.includes("13_evidence/private_version_35_s5_t3_controlled_private_deployment_and_rollback.json"),
    true,
  );
  assert.equal(
    ledger.evidence_files.includes("13_evidence/version_37_s5_t3_public_deployment_and_recovery.json"),
    true,
  );
  assert.equal(
    ledger.evidence_files.includes("13_evidence/public_version_126_habit_feedback.json"),
    true,
  );
  assert.equal(
    ledger.evidence_files.includes("13_evidence/public_version_125_rollback_restore.json"),
    true,
  );
  assert.equal(ledger.public_deploy_eligible, false);
});

test("Version 35 storage mapping boundary retains only read-only aggregate evidence", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_35_s5_t3_storage_mapping_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S5-T3");
  assert.equal(
    evidence.status,
    "NOT_PROVEN_SITES_TARGET_NOT_RESOLVED_THROUGH_AUTHORIZED_WORKERS_CATALOGUE",
  );
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.authorized_cloudflare_readback.account_identity_resolved, true);
  assert.equal(evidence.authorized_cloudflare_readback.d1_catalogue_read, true);
  assert.equal(evidence.authorized_cloudflare_readback.d1_catalogue_entry_count, 4);
  assert.equal(evidence.authorized_cloudflare_readback.r2_bucket_catalogue_read, true);
  assert.equal(evidence.authorized_cloudflare_readback.r2_bucket_catalogue_entry_count, 10);
  assert.equal(evidence.authorized_cloudflare_readback.sites_worker_present_in_authorized_catalogue, false);
  assert.deepEqual(evidence.authorized_cloudflare_readback.sites_worker_settings_http_statuses, [404]);
  assert.equal(evidence.reconciliation.d1_binding_matches_authenticated_catalogue, false);
  assert.equal(evidence.reconciliation.r2_binding_matches_authenticated_catalogue, false);
  assert.equal(evidence.safety_boundary.runtime_values_read_or_logged, false);
  assert.equal(evidence.safety_boundary.resource_names_or_identifiers_recorded, false);
  assert.equal(evidence.safety_boundary.database_tables_or_records_read, false);
  assert.equal(evidence.safety_boundary.r2_objects_or_object_metadata_read, false);
  assert.equal(evidence.safety_boundary.r2_write_operations_called, false);
  assert.equal(evidence.safety_boundary.storage_class_or_billing_status_inferred, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 34 S5-T2 configuration evidence preserves value-free private continuity", async () => {
  const configuration = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_34_s5_t2_runtime_configuration.json", import.meta.url),
      "utf8",
    ),
  );
  const boundary = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_34_s5_t2_local_shell_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify({ configuration, boundary });

  assert.equal(configuration.task_id, "S5-T2");
  assert.equal(configuration.status, "PASS_PRIVATE_RUNTIME_CONFIGURATION_PRESENCE_ONLY");
  assert.equal(configuration.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(configuration.candidate.saved_version_number, 34);
  assert.equal(configuration.candidate.source_readback_present, true);
  assert.equal(configuration.candidate.archive_readback_present, true);
  assert.equal(configuration.candidate.configuration_revision_unchanged_from_prior_private_configuration_evidence, true);
  assert.equal(configuration.configuration_presence.revision, 8);
  assert.equal(configuration.configuration_presence.entry_count, 15);
  assert.equal(configuration.configuration_presence.secret_entry_count, 11);
  assert.equal(configuration.configuration_presence.non_secret_entry_count, 4);
  assert.equal(configuration.configuration_presence.required_auth_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_email_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_privacy_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_abuse_protection_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_origin_key_type_present, true);
  assert.equal(configuration.configuration_presence.configuration_values_inspected, false);
  assert.equal(configuration.configuration_presence.configuration_values_recorded, false);
  assert.equal(configuration.private_site_state.site_active, true);
  assert.equal(configuration.private_site_state.current_user_role, "owner");
  assert.equal(configuration.private_site_state.access_mode, "custom");
  assert.equal(configuration.private_site_state.allowed_users_count, 1);
  assert.equal(configuration.private_site_state.allowed_groups_count, 0);
  assert.equal(configuration.private_site_state.external_visitor_count, 0);
  assert.equal(configuration.owner_gate_support.asset_authorization, "PASS_FINAL_AUTHORIZED_ASSETS");
  assert.equal(configuration.owner_gate_support.privacy_contract_tests, "PASS_3_OF_3");
  assert.equal(configuration.scope_and_limits.deployment_action_called, false);
  assert.equal(configuration.scope_and_limits.public_audience_changed, false);
  assert.equal(configuration.scope_and_limits.github_uploaded, false);
  assert.equal(boundary.status, "NOT_HOSTED_CONFIGURATION_TEST");
  assert.equal(boundary.execution.hosted_configuration_missing_inferred, false);
  assert.equal(boundary.execution.protected_runtime_values_injected_into_local_shell, false);
  assert.equal(boundary.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 34 S5-T3 private deployment and rollback evidence does not overclaim browser E2E", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_34_s5_t3_controlled_private_deployment_and_rollback.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S5-T3");
  assert.equal(evidence.phase, "S5-T3");
  assert.equal(evidence.status, "PASS_CONTROLLED_PRIVATE_DEPLOY_AND_ROLLBACK_PARTIAL");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.candidate.saved_version_number, 34);
  assert.equal(evidence.candidate.source_readback_matches_saved_candidate, true);
  assert.equal(evidence.candidate.archive_stored_by_sites, true);
  assert.equal(evidence.private_access.site_active, true);
  assert.equal(evidence.private_access.current_user_role, "owner");
  assert.equal(evidence.private_access.access_mode, "custom");
  assert.equal(evidence.private_access.allowed_user_count, 1);
  assert.equal(evidence.private_access.allowed_group_count, 0);
  assert.equal(evidence.private_access.external_visitor_count, 0);
  assert.equal(evidence.controlled_private_deployment.deployed_version_number, 34);
  assert.equal(evidence.controlled_private_deployment.terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.rollback_version_number, 33);
  assert.equal(evidence.rollback_and_restore.rollback_terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.restore_version_number, 34);
  assert.equal(evidence.rollback_and_restore.restore_terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.private_access_preserved_after_rollback_and_restore, true);
  assert.equal(evidence.post_restore_observation.error_event_count, 0);
  assert.equal(evidence.post_restore_observation.log_bodies_retained, false);
  assert.equal(evidence.controlled_browser_e2e.browser_control_runtime_available, false);
  assert.equal(evidence.controlled_browser_e2e.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.controlled_browser_e2e.sites_bypass_token_generated_or_used, false);
  assert.equal(
    evidence.controlled_browser_e2e.email_registration_verification_reset_and_signin,
    "NOT_RUN_NO_CONTROLLED_BROWSER_EXECUTOR",
  );
  assert.equal(
    evidence.controlled_browser_e2e.a_b_tenant_isolation_and_second_device_history,
    "NOT_RUN_NO_CONTROLLED_BROWSER_EXECUTOR",
  );
  assert.equal(
    evidence.controlled_browser_e2e.d1_r2_reconciliation,
    "NOT_RUN_NO_AUTHENTICATED_CLOUDFLARE_STORAGE_CATALOGUE",
  );
  assert.equal(evidence.cloudflare_storage_catalogue_boundary.wrangler_v4_available, true);
  assert.equal(evidence.cloudflare_storage_catalogue_boundary.authenticated, false);
  assert.equal(
    evidence.cloudflare_storage_catalogue_boundary.configuration_values_or_resource_catalogues_read,
    false,
  );
  assert.equal(evidence.scope_and_limits.public_audience_changed, false);
  assert.equal(evidence.scope_and_limits.github_uploaded, false);
  assert.equal(evidence.scope_and_limits.product_pass_claimed, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 33 S5-T2 configuration evidence preserves private configuration continuity", async () => {
  const configuration = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_33_s5_t2_runtime_configuration.json", import.meta.url),
      "utf8",
    ),
  );
  const boundary = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_33_s5_t2_local_shell_boundary.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify({ configuration, boundary });

  assert.equal(configuration.task_id, "S5-T2");
  assert.equal(configuration.status, "PASS_PRIVATE_RUNTIME_CONFIGURATION_PRESENCE_ONLY");
  assert.equal(configuration.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(configuration.candidate.saved_version_number, 33);
  assert.equal(configuration.candidate.configuration_revision_unchanged_from_prior_private_configuration_evidence, true);
  assert.equal(configuration.configuration_presence.revision, 8);
  assert.equal(configuration.configuration_presence.entry_count, 15);
  assert.equal(configuration.configuration_presence.secret_entry_count, 11);
  assert.equal(configuration.configuration_presence.non_secret_entry_count, 4);
  assert.equal(configuration.configuration_presence.required_auth_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_email_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_privacy_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_abuse_protection_key_types_present, true);
  assert.equal(configuration.configuration_presence.required_origin_key_type_present, true);
  assert.equal(configuration.configuration_presence.configuration_values_inspected, false);
  assert.equal(configuration.private_site_state.access_mode, "custom");
  assert.equal(configuration.private_site_state.allowed_users_count, 1);
  assert.equal(configuration.private_site_state.allowed_groups_count, 0);
  assert.equal(configuration.private_site_state.external_visitor_count, 0);
  assert.equal(configuration.scope_and_limits.deployment_action_called, false);
  assert.equal(configuration.scope_and_limits.public_audience_changed, false);
  assert.equal(boundary.status, "NOT_HOSTED_CONFIGURATION_TEST");
  assert.equal(boundary.execution.hosted_configuration_missing_inferred, false);
  assert.equal(boundary.execution.protected_runtime_values_injected_into_local_shell, false);
  assert.equal(boundary.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 33 S5-T3 private deployment and rollback evidence does not overclaim browser E2E", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_33_s5_t3_controlled_private_deployment_and_rollback.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.phase, "S5-T3");
  assert.equal(evidence.status, "PASS_CONTROLLED_PRIVATE_DEPLOY_AND_ROLLBACK_PARTIAL");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.candidate.saved_version_number, 33);
  assert.equal(evidence.private_access.access_mode, "custom");
  assert.equal(evidence.private_access.allowed_user_count, 1);
  assert.equal(evidence.private_access.allowed_group_count, 0);
  assert.equal(evidence.private_access.external_visitor_count, 0);
  assert.equal(evidence.current_site_identity.brand_title_matches_personal_schedule, true);
  assert.equal(evidence.current_site_identity.mydairy_custom_domain_present, true);
  assert.equal(evidence.current_site_identity.mydairy_custom_domain_status, "active");
  assert.equal(evidence.current_site_identity.mydairy_custom_domain_provider_status, "active");
  assert.equal(evidence.current_site_identity.mydairy_custom_domain_ssl_status, "active");
  assert.equal(evidence.current_site_identity.raw_hostname_recorded, false);
  assert.equal(evidence.controlled_private_deployment.terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.rollback_version_number, 32);
  assert.equal(evidence.rollback_and_restore.rollback_terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.restore_version_number, 33);
  assert.equal(evidence.rollback_and_restore.restore_terminal_status, "succeeded");
  assert.equal(evidence.rollback_and_restore.private_access_preserved_after_rollback_and_restore, true);
  assert.equal(evidence.post_deployment_observation.initial_deployment_error_event_count, 0);
  assert.equal(evidence.post_deployment_observation.post_restore_error_event_count, 0);
  assert.equal(evidence.post_deployment_observation.log_bodies_retained, false);
  assert.equal(evidence.controlled_browser_e2e.browser_control_runtime_available, false);
  assert.equal(evidence.controlled_browser_e2e.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.controlled_browser_e2e.sites_bypass_token_generated_or_used, false);
  assert.equal(evidence.current_local_contract_revalidation.authentication_and_mail_contract, "PASS_LOCAL_CONTRACT");
  assert.equal(evidence.current_local_contract_revalidation.tenant_isolation_contract, "PASS_LOCAL_CONTRACT");
  assert.equal(evidence.current_local_contract_revalidation.privacy_consent_contract, "PASS_LOCAL_CONTRACT");
  assert.equal(evidence.current_local_contract_revalidation.api_and_storage_binding_contract, "PASS_LOCAL_CONTRACT");
  assert.equal(evidence.current_local_contract_revalidation.primary_menu_and_workbench_regression, "PASS_LOCAL_CONTRACT");
  assert.equal(evidence.current_local_contract_revalidation.user_audited_interaction_bindings, "PASS_LOCAL_UI_BINDING_CONTRACT");
  assert.equal(evidence.current_local_contract_revalidation.current_production_browser_e2e, "NOT_RUN_NO_CONTROLLED_BROWSER_EXECUTOR");
  assert.equal(evidence.change_boundary.public_audience_changed, false);
  assert.equal(evidence.change_boundary.github_uploaded, false);
  assert.equal(evidence.change_boundary.product_pass_claimed, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
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

test("Version 31 post-restore error check retains no worker log material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_31_post_restore_error_log_check.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 31);
  assert.equal(evidence.candidate.rollback_restore_rehearsal_succeeded, true);
  assert.equal(evidence.read_only_query.errors_only, true);
  assert.equal(evidence.read_only_query.since_minutes, 10);
  assert.equal(evidence.read_only_query.limit, 20);
  assert.equal(evidence.read_only_query.worker_error_event_count, 0);
  assert.equal(evidence.read_only_query.raw_log_messages_recorded, false);
  assert.equal(evidence.read_only_query.request_identifiers_recorded, false);
  assert.equal(evidence.read_only_query.route_or_user_data_recorded, false);
  assert.equal(evidence.post_restore_control_plane.latest_saved_version_number, 31);
  assert.equal(evidence.post_restore_control_plane.approved_version_source_matches_expected, true);
  assert.equal(evidence.local_validation.lint, "PASS");
  assert.equal(evidence.local_validation.release_evidence, "PASS_46_OF_46");
  assert.equal(evidence.local_validation.release_verifier, "PASS_BUILD_LAST_MILE_READINESS");
  assert.equal(evidence.local_validation.diff_check, "PASS");
  assert.equal(evidence.result.post_restore_narrow_error_only_window_has_visible_p0, false);
  assert.equal(evidence.result.current_v31_production_p0_absence_fully_proven, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
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

test("Version 31 email browser boundary recheck retains no mailbox, account, session, or navigation material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_31_email_browser_security_boundary_recheck.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 31);
  assert.equal(evidence.candidate.candidate_identity_inherited_from_prior_v31_gate_audit, true);
  assert.equal(evidence.candidate.access_policy_or_public_audience_changed_in_this_increment, false);
  assert.equal(evidence.controlled_browser_attempt.fresh_agent_test_tab_created, true);
  assert.equal(evidence.controlled_browser_attempt.existing_user_tab_claimed, false);
  assert.equal(evidence.controlled_browser_attempt.target_route, "/auth/sign-up");
  assert.equal(evidence.controlled_browser_attempt.navigation_completed, false);
  assert.equal(evidence.controlled_browser_attempt.signup_page_rendered, false);
  assert.equal(evidence.controlled_browser_attempt.static_visible_dom_checked, false);
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
  assert.equal(evidence.scope_and_cleanup.existing_user_tab_or_session_inspected, false);
  assert.equal(evidence.scope_and_cleanup.temporary_test_tab_finalized, true);
  assert.equal(evidence.scope_and_cleanup.temporary_application_account_created, false);
  assert.equal(evidence.result.current_v31_email_registration_verification_reset_signin_proven, false);
  assert.equal(evidence.result.repeated_navigation_boundary_observed, true);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("current S4-T3A readiness evidence only permits a private saved-version next step", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/s4_t3a_current_candidate_readiness.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S4-T3A");
  assert.equal(evidence.status, "READINESS_PASS");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.subject.source_commit.length, 40);
  assert.equal(evidence.subject.source_tree.length, 40);
  assert.equal(evidence.subject.working_tree_clean_after_review, true);
  assert.equal(evidence.frozen_sequence.five_frozen_file_bindings_match, true);
  assert.equal(evidence.frozen_sequence.sequence_validator, "PASS_SEQUENCE_ADDENDUM_INTEGRITY_ONLY");
  assert.equal(evidence.frozen_sequence.sequence_tests, "PASS_4_OF_4");
  assert.equal(evidence.independent_review.separate_context, true);
  assert.equal(evidence.independent_review.sensitive_first_write.server_identity_and_consent_before_body, true);
  assert.equal(evidence.independent_review.sensitive_first_write.client_tenant_fields_absent, true);
  assert.equal(evidence.scope_and_limits.private_s5_t1_saved_version_allowed_next, true);
  assert.equal(evidence.scope_and_limits.saved_version_created_in_this_phase, false);
  assert.equal(evidence.scope_and_limits.deployment_action_called, false);
  assert.equal(evidence.scope_and_limits.sites_or_access_policy_changed, false);
  assert.equal(evidence.scope_and_limits.public_audience_change_allowed, false);
  assert.equal(evidence.scope_and_limits.browser_or_visual_runtime_equivalence, "NOT_RUN");
  assert.equal(evidence.scope_and_limits.product_pass_claimed, false);
  assert.equal(evidence.scope_and_limits.final_acceptance_claimed, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("dependent local-sync S4-T3A readiness remains a private-candidate gate", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/s4_t3a_dependent_local_sync_readiness.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S4-T3A");
  assert.equal(evidence.status, "READINESS_PASS");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.subject.source_commit.length, 40);
  assert.equal(evidence.subject.source_tree.length, 40);
  assert.equal(evidence.subject.working_tree_clean_after_review, true);
  assert.equal(evidence.frozen_sequence.five_frozen_file_bindings_match, true);
  assert.equal(evidence.frozen_sequence.sequence_validator, "PASS_SEQUENCE_ADDENDUM_INTEGRITY_ONLY");
  assert.equal(evidence.independent_review.separate_context, true);
  assert.equal(evidence.independent_review.local_checks.workbench_data, "PASS");
  assert.equal(evidence.independent_review.local_checks.build, "PASS");
  assert.equal(evidence.independent_review.dependent_local_sync.local_parent_identifier_never_sent_to_cloud, true);
  assert.equal(evidence.independent_review.dependent_local_sync.child_cache_failure_still_marks_parent_dependency, true);
  assert.equal(evidence.independent_review.dependent_local_sync.same_account_alias_replaces_only_a_payload_copy, true);
  assert.equal(evidence.scope_and_limits.private_s5_t1_saved_version_allowed_next, true);
  assert.equal(evidence.scope_and_limits.saved_version_created_in_this_phase, false);
  assert.equal(evidence.scope_and_limits.deployment_action_called, false);
  assert.equal(evidence.scope_and_limits.public_audience_change_allowed, false);
  assert.equal(evidence.scope_and_limits.s5_real_evidence, "NOT_RUN");
  assert.equal(evidence.scope_and_limits.product_pass_claimed, false);
  assert.equal(evidence.scope_and_limits.final_acceptance_claimed, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("tenant-storage S4-T3A readiness remains a private-candidate gate", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/s4_t3a_tenant_storage_readiness.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S4-T3A");
  assert.equal(evidence.status, "READINESS_PASS");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.subject.source_commit.length, 40);
  assert.equal(evidence.subject.source_tree.length, 40);
  assert.equal(evidence.subject.working_tree_clean_after_review, true);
  assert.equal(evidence.frozen_sequence.five_frozen_file_bindings_match, true);
  assert.equal(evidence.frozen_sequence.sequence_validator, "PASS_SEQUENCE_ADDENDUM_INTEGRITY_ONLY");
  assert.equal(evidence.independent_review.separate_context, true);
  assert.equal(evidence.independent_review.local_checks.lint, "PASS");
  assert.equal(evidence.independent_review.local_checks.typecheck, "PASS");
  assert.equal(evidence.independent_review.local_checks.tenant_store_integration, "PASS");
  assert.equal(evidence.independent_review.tenant_storage.account_a_records_not_visible_to_account_b, true);
  assert.equal(evidence.independent_review.tenant_storage.foreign_account_record_mutation_rejected, true);
  assert.equal(evidence.independent_review.tenant_storage.cross_account_habit_checkin_parent_reference_rejected, true);
  assert.equal(evidence.independent_review.tenant_storage.cross_account_savings_transaction_parent_reference_rejected, true);
  assert.equal(evidence.independent_review.dependent_local_sync.unrecognized_resource_returns_no_dependency, true);
  assert.equal(evidence.independent_review.dependent_local_sync.immediate_and_replay_requests_resolve_local_parent_reference_before_fetch, true);
  assert.equal(evidence.scope_and_limits.private_s5_t1_saved_version_allowed_next, true);
  assert.equal(evidence.scope_and_limits.saved_version_created_in_this_phase, false);
  assert.equal(evidence.scope_and_limits.deployment_action_called, false);
  assert.equal(evidence.scope_and_limits.sites_or_access_policy_changed, false);
  assert.equal(evidence.scope_and_limits.public_audience_change_allowed, false);
  assert.equal(evidence.scope_and_limits.s5_real_evidence, "NOT_RUN");
  assert.equal(evidence.scope_and_limits.product_pass_claimed, false);
  assert.equal(evidence.scope_and_limits.final_acceptance_claimed, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("session-scope S4-T3A readiness only unlocks a private candidate", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/s4_t3a_session_scope_timeout_readiness.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.task_id, "S4-T3A");
  assert.equal(evidence.status, "READINESS_PASS");
  assert.equal(evidence.verdict, "NOT_PRODUCT_ACCEPTANCE");
  assert.equal(evidence.subject.source_commit.length, 40);
  assert.equal(evidence.subject.source_tree.length, 40);
  assert.equal(evidence.subject.working_tree_clean_after_review, true);
  assert.equal(evidence.subject.diff_check, "PASS");
  assert.equal(evidence.frozen_sequence.five_frozen_file_bindings_match, true);
  assert.equal(evidence.frozen_sequence.sequence_validator, "PASS_SEQUENCE_ADDENDUM_INTEGRITY_ONLY");
  assert.equal(evidence.independent_review.fresh_read_only_post_commit_review, true);
  assert.equal(evidence.independent_review.builder_observations_not_used_as_verdict, true);
  assert.equal(evidence.independent_review.local_checks.workbench_data, "PASS_20_OF_20");
  assert.equal(evidence.independent_review.local_checks.tenant_store_integration, "PASS_4_OF_4");
  assert.equal(evidence.independent_review.session_scope_recovery.stalled_session_request_is_aborted, true);
  assert.equal(evidence.independent_review.session_scope_recovery.stalled_session_request_reaches_isolated_guest_partition, true);
  assert.equal(evidence.independent_review.session_scope_recovery.guest_records_are_not_replayed_under_a_later_account, true);
  assert.equal(evidence.independent_review.interactive_history_paths.normal_menu_routes_do_not_enter_reference_only_mode, true);
  assert.equal(evidence.independent_review.tenant_and_sync_boundaries.account_a_records_are_invisible_and_immutable_to_account_b, true);
  assert.equal(evidence.independent_review.tenant_and_sync_boundaries.immediate_and_replay_requests_resolve_local_parent_alias_before_fetch, true);
  assert.equal(evidence.scope_and_limits.private_s5_t1_saved_version_allowed_next, true);
  assert.equal(evidence.scope_and_limits.saved_version_created_in_this_phase, false);
  assert.equal(evidence.scope_and_limits.deployment_action_called, false);
  assert.equal(evidence.scope_and_limits.sites_or_access_policy_changed, false);
  assert.equal(evidence.scope_and_limits.public_audience_change_allowed, false);
  assert.equal(evidence.scope_and_limits.browser_or_visual_runtime_equivalence, "NOT_RUN");
  assert.equal(evidence.scope_and_limits.product_pass_claimed, false);
  assert.equal(evidence.scope_and_limits.final_acceptance_claimed, false);
  assert.equal(evidence.scope_and_limits.github_uploaded, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(evidence.real_user_business_data_read_or_written, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 31 browserless auth preflight retains no access, mailbox, or captcha material", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_31_browserless_auth_preflight.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 31);
  assert.equal(evidence.candidate.site_active, true);
  assert.equal(evidence.candidate.current_user_role, "owner");
  assert.equal(evidence.candidate.access_mode, "custom");
  assert.equal(evidence.candidate.allowed_user_count, 1);
  assert.equal(evidence.candidate.allowed_group_count, 0);
  assert.equal(evidence.candidate.external_visitor_count, 0);
  assert.equal(evidence.browserless_entry_probe.requests_sent_without_credentials, true);
  assert.equal(evidence.browserless_entry_probe.browser_or_sites_bypass_used, false);
  assert.equal(evidence.browserless_entry_probe.cookie_or_storage_used, false);
  assert.equal(evidence.browserless_entry_probe.sign_up_route_status, 401);
  assert.equal(evidence.browserless_entry_probe.sign_in_route_status, 401);
  assert.equal(evidence.browserless_entry_probe.forgot_password_route_status, 401);
  assert.equal(evidence.browserless_entry_probe.public_config_route_status, 401);
  assert.equal(evidence.browserless_entry_probe.unauthenticated_profile_route_status, 401);
  assert.equal(evidence.browserless_entry_probe.public_config_json_readable, false);
  assert.equal(evidence.browserless_entry_probe.turnstile_site_key_observed_from_current_live_public_config, false);
  assert.equal(evidence.local_auth_contract.email_sign_up_sign_in_and_reset_request_require_natural_turnstile_response, true);
  assert.equal(evidence.local_auth_contract.browserless_captcha_response_forged_or_reused, false);
  assert.equal(evidence.controlled_mailbox_preflight.gmail_connector_readable, true);
  assert.equal(evidence.controlled_mailbox_preflight.gmail_profile_values_retained_in_evidence, false);
  assert.equal(evidence.controlled_mailbox_preflight.mailbox_content_search_or_read_performed, false);
  assert.equal(evidence.controlled_mailbox_preflight.mailbox_write_performed, false);
  assert.equal(evidence.result.safe_browserless_email_auth_submission_available, false);
  assert.equal(evidence.result.current_v31_email_registration_verification_reset_signin_proven, false);
  assert.equal(evidence.scope_and_cleanup.temporary_application_account_created, false);
  assert.equal(evidence.scope_and_cleanup.browser_cookie_or_storage_inspected, false);
  assert.equal(evidence.scope_and_cleanup.real_user_business_data_read_or_written, false);
  assert.equal(evidence.sensitive_values_recorded, false);
  assert.equal(serialized.includes("@"), false);
  assert.equal(serialized.includes("token="), false);
  assert.equal(serialized.includes("Bearer "), false);
});

test("Version 31 S5-T3 gate audit keeps current production proof distinct from historical support", async () => {
  const evidence = JSON.parse(
    await readFile(
      new URL("../13_evidence/private_version_31_s5_t3_gate_audit.json", import.meta.url),
      "utf8",
    ),
  );
  const serialized = JSON.stringify(evidence);

  assert.equal(evidence.candidate.sites_version_number, 31);
  assert.equal(evidence.frozen_taskpack_binding.task_dag_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.acceptance_contract_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.oracles_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.traceability_matrix_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.owner_approval_sha256.length, 64);
  assert.equal(evidence.frozen_taskpack_binding.frozen_file_count, 5);
  assert.equal(evidence.frozen_taskpack_binding.frozen_files_all_match_current_taskpack, true);
  assert.equal(evidence.frozen_taskpack_binding.sequence_addendum_validation, "PASS_SEQUENCE_ADDENDUM_INTEGRITY_ONLY");
  assert.equal(evidence.frozen_taskpack_binding.requirement_count, 15);
  assert.equal(evidence.current_control_plane.latest_saved_version_number, 31);
  assert.equal(evidence.current_control_plane.latest_saved_version_source_matches_expected, true);
  assert.equal(evidence.gate_assessment.r003_real_authentication.status, "PARTIAL");
  assert.equal(
    evidence.gate_assessment.r003_real_authentication.current_v31_browserless_preflight,
    "NOT_PROVEN_PRIVATE_SITE_ACCESS_GATE_BLOCKS_UNCREDENTIALED_ENTRY_AND_NO_NATURAL_TURNSTILE_RESPONSE_IS_AVAILABLE",
  );
  assert.equal(evidence.gate_assessment.r004_a_b_isolation.current_v31_physical_a_b_replay, "NOT_RUN");
  assert.equal(
    evidence.gate_assessment.r005_d1_r2_persistence.current_v31_physical_mapping_or_record_object_reconciliation,
    "NOT_PROVEN",
  );
  assert.equal(evidence.gate_assessment.r009_saved_version_rollback_restore.status, "PASS");
  assert.equal(
    evidence.gate_assessment.r009_saved_version_rollback_restore.current_v31_rollback_then_restore,
    "PASS_PRIVATE_VERSION_31_TO_30_TO_31_OWNER_ONLY",
  );
  assert.equal(evidence.gate_assessment.r011_cross_device_crud_and_history.current_v31_physical_cross_device_history, "NOT_RUN");
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
