#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const args = process.argv.slice(2);
const allowPlaceholders = args.includes('--allow-placeholders');
const positional = args.filter((x) => x !== '--allow-placeholders');
if (positional.length !== 2) {
  console.error('usage: validate_config.js [--allow-placeholders] <env-file> <workspaces.json>');
  process.exit(2);
}
const [envPath, workspacePath] = positional;

function parseEnv(text) {
  const out = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const index = line.indexOf('=');
    if (index <= 0) throw new Error(`invalid env line: ${raw}`);
    out[line.slice(0, index).trim()] = line.slice(index + 1).trim();
  }
  return out;
}

const env = parseEnv(fs.readFileSync(envPath, 'utf8'));
const workspaces = JSON.parse(fs.readFileSync(workspacePath, 'utf8'));
const errors = [];

for (const key of [
  'CYBERBOSS_RUNTIME',
  'CYBERBOSS_CODEX_ENDPOINT',
  'CYBERBOSS_WORKSPACE_ROOT',
  'CB_RUNTIME_DB',
  'CB_JOB_CONCURRENCY',
  'CB_DATA_REPO_SLUG',
  'CB_DATA_AREA',
  'CB_DATA_DOMAIN',
  'CB_PRIVATE_DB_CLIENT',
  'CB_PRIVATE_DB_AUTH_MODE',
  'CB_IDENTITY_SCOPE_POLICY',
  'CB_APP_REPO_SLUG',
  'CB_APP_SUBPATH',
  'CB_INCOMING_ROOT',
  'CB_R2_BUCKET',
  'CB_R2_PREFIX',
  'CB_OCI_BUCKET_FILE',
  'CB_OCI_PREFIX',
  'CB_PROVIDER_ACTIVATION_CONFIG',
]) {
  if (!env[key]) errors.push(`missing:${key}`);
}
if (!allowPlaceholders) {
  for (const [key, value] of Object.entries(env)) {
    if (/REPLACE_/i.test(value)) errors.push(`placeholder:${key}`);
  }
}
if (!/^ws:\/\/(127\.0\.0\.1|localhost):\d+$/.test(env.CYBERBOSS_CODEX_ENDPOINT || '')) {
  errors.push('codex_endpoint_not_loopback');
}
if (Number(env.CB_JOB_CONCURRENCY) !== 1) errors.push('job_concurrency_must_equal_1');
if (env.CB_CLAUDE_RUNTIME !== 'false') errors.push('claude_runtime_must_default_false');
if (env.CB_FILE_ATTACHMENTS !== 'false') errors.push('attachments_must_default_false');
if (env.CB_AUTONOMOUS_MUTATION !== 'false') errors.push('autonomous_mutation_must_default_false');
if (env.CB_PRIVATE_DB_CANONICAL_SYNC !== 'true') errors.push('private_db_sync_must_default_true');
if (env.CB_DATA_REPO_SLUG !== 'LinzeColin/Private-Database') errors.push('private_db_repo_identity');
if (env.CB_DATA_AREA !== 'Private-MetaDatabase') errors.push('private_db_area');
if (env.CB_DATA_DOMAIN !== 'CyberBoss') errors.push('private_db_domain');
if (env.CB_PRIVATE_DB_AUTH_MODE !== 'gh-login') errors.push('private_db_auth_mode');
if (env.CB_R2_BUCKET !== 'cyberboss-cold') errors.push('r2_bucket_scope');
if (env.CB_R2_PREFIX !== 'ovh-singapore-vps-1/') errors.push('r2_prefix_scope');
if (env.CB_OCI_PREFIX !== 'cyberboss-cold-backup/ovh-singapore-vps-1/') errors.push('oci_prefix_scope');
if (env.CB_APP_REPO_SLUG !== 'LinzeColin/MetaDatabase') errors.push('code_repo_identity');
if (env.CB_APP_SUBPATH !== 'CyberBoss') errors.push('code_subpath_identity');
for (const forbidden of ['CB_DATA_REPO_PATH', 'CB_DATA_REPO_URL', 'CB_DATA_ROOT', 'CB_APP_REPO_URL']) {
  if (Object.hasOwn(env, forbidden)) errors.push(`forbidden_env:${forbidden}`);
}

if (workspaces.schema_version !== 1) errors.push('workspace_schema_version');
if (!workspaces.workspaces || typeof workspaces.workspaces !== 'object') errors.push('workspaces_missing');
if (workspaces.default_alias !== 'cyberboss') errors.push('default_alias_must_be_cyberboss');
if (Object.keys(workspaces.workspaces || {}).length !== 1) errors.push('mvp_requires_one_workspace');
const root = path.resolve(env.CYBERBOSS_WORKSPACE_ROOT || '/srv/cyberboss-workspaces');
for (const [alias, config] of Object.entries(workspaces.workspaces || {})) {
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(alias)) errors.push(`invalid_alias:${alias}`);
  if (!config.root) { errors.push(`missing_root:${alias}`); continue; }
  const resolved = path.resolve(config.root);
  if (!(resolved === root || resolved.startsWith(`${root}${path.sep}`))) errors.push(`workspace_outside_root:${alias}`);
  if (!Number.isFinite(Number(config.max_bytes)) || Number(config.max_bytes) <= 0) errors.push(`invalid_max_bytes:${alias}`);
  if (config.repo !== 'LinzeColin/MetaDatabase') errors.push(`workspace_repo_identity:${alias}`);
  if (config.project_subpath !== 'CyberBoss') errors.push(`workspace_subpath:${alias}`);
  if (JSON.stringify(config.write_globs) !== JSON.stringify(['CyberBoss/**'])) errors.push(`workspace_write_scope:${alias}`);
  if (!Array.isArray(config.sparse_paths) || !config.sparse_paths.includes('CyberBoss')) errors.push(`workspace_sparse_path:${alias}`);
  if (!Array.isArray(config.allowed_branches) || !config.allowed_branches.includes('codex/cyberboss-*')) {
    errors.push(`workspace_branch_policy:${alias}`);
  }
}
if (!workspaces.workspaces?.[workspaces.default_alias]) errors.push('default_alias_unknown');

const policyPath = path.join(path.dirname(envPath), 'identity-scope.policy.json');
if (!fs.existsSync(policyPath)) {
  errors.push('identity_scope_policy_missing');
} else {
  const policy = JSON.parse(fs.readFileSync(policyPath, 'utf8'));
  if (policy.schema_version !== 1) errors.push('identity_scope_policy_schema');
  if (policy.code?.repository !== env.CB_APP_REPO_SLUG) errors.push('policy_code_repo_mismatch');
  if (policy.code?.project_subpath !== env.CB_APP_SUBPATH) errors.push('policy_code_subpath_mismatch');
  if (policy.code?.workspace_alias !== workspaces.default_alias) errors.push('policy_alias_mismatch');
  if (JSON.stringify(policy.code?.allowed_write_globs) !== JSON.stringify(['CyberBoss/**'])) errors.push('policy_write_scope');
  if (policy.code?.new_repository_allowed !== false) errors.push('policy_new_repo');
  if (policy.data?.repository !== env.CB_DATA_REPO_SLUG) errors.push('policy_data_repo_mismatch');
  if (policy.data?.area !== env.CB_DATA_AREA) errors.push('policy_data_area_mismatch');
  if (policy.data?.domain !== env.CB_DATA_DOMAIN) errors.push('policy_data_domain_mismatch');
  if (policy.data?.access_mode !== 'no_clone_client') errors.push('policy_data_access_mode');
  if (policy.cloudflare?.r2?.bucket !== env.CB_R2_BUCKET) errors.push('policy_r2_bucket_mismatch');
  if (policy.cloudflare?.r2?.object_prefix !== env.CB_R2_PREFIX) errors.push('policy_r2_prefix_mismatch');
  if (policy.oci?.object_prefix !== env.CB_OCI_PREFIX) errors.push('policy_oci_prefix_mismatch');
}

if (errors.length) {
  for (const error of errors) console.error(`ERROR=${error}`);
  console.error('CONFIG_VALIDATION=FAIL');
  process.exit(1);
}
console.log(`CONFIG_VALIDATION=PASS workspaces=${Object.keys(workspaces.workspaces).length}`);
