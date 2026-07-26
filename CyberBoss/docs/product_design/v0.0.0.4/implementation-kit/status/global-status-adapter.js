#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const sourcePath = process.env.CB_STATUS_SOURCE_PATH || '/var/lib/cyberboss/status/snapshot.json';
const sourceUrl = process.env.CB_STATUS_SOURCE_URL || '';
const output = process.env.CB_GLOBAL_STATUS_OUTPUT || '/var/lib/cyberboss/status/global-project-row.json';
const maxAgeSeconds = Number(process.env.CB_STATUS_MAX_AGE_SECONDS || 120);

function severity(value) {
  return ['healthy', 'degraded', 'stopped', 'activation_pending', 'not_verified'].includes(value) ? value : 'not_verified';
}

async function loadSnapshot() {
  if (fs.existsSync(sourcePath)) {
    return JSON.parse(fs.readFileSync(sourcePath, 'utf8'));
  }
  if (!sourceUrl) throw new Error(`local snapshot missing and CB_STATUS_SOURCE_URL unset: ${sourcePath}`);
  const clientId = process.env.CF_ACCESS_CLIENT_ID;
  const clientSecret = process.env.CF_ACCESS_CLIENT_SECRET;
  if (!clientId || !clientSecret) throw new Error('remote snapshot requires Cloudflare Access service token');
  const response = await fetch(sourceUrl, {
    headers: {
      'CF-Access-Client-Id': clientId,
      'CF-Access-Client-Secret': clientSecret,
      Accept: 'application/json',
    },
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error(`snapshot HTTP ${response.status}`);
  return response.json();
}

(async () => {
  const snapshot = await loadSnapshot();
  const generated = new Date(snapshot.generated_at);
  const age = Number.isNaN(generated.getTime()) ? Infinity : Math.max(0, (Date.now() - generated.getTime()) / 1000);
  const stale = age > maxAgeSeconds;
  const state = stale ? 'degraded' : severity(snapshot.service?.state);

  const row = {
    schema_version: 1,
    project: 'CyberBoss Cloud',
    url: 'https://cyberboss.linzezhang.com',
    composition: 'WeChat bridge + Codex Runtime + Timeline + canonical sync',
    runtime_host: 'OVH Singapore VPS-1',
    database: 'Private-MetaDatabase canonical objects + SQLite runtime spool',
    file_storage: 'Cloudflare R2 cold + OCI backup',
    deployment: 'GitHub Actions + systemd immutable releases',
    backup: 'SQLite online snapshot -> R2 -> OCI selected copy',
    agent_dependency: 'Product jobs use Codex; status/self-heal/backup do not use Agent tokens',
    state,
    generated_at: new Date().toISOString(),
    source_generated_at: snapshot.generated_at || null,
    source_age_seconds: Number.isFinite(age) ? Math.round(age) : null,
    summary: {
      version: snapshot.service?.version || 'unknown',
      resource_profile: snapshot.resources?.profile || 'unselected',
      wechat: snapshot.wechat?.state || 'unknown',
      runtime: snapshot.runtime?.state || 'unknown',
      queue: snapshot.queue?.queued ?? null,
      canonical: snapshot.canonical?.state || 'unknown',
      timeline: snapshot.timeline?.build_state || 'unknown',
      r2: snapshot.backup?.r2_state || 'unknown',
      oci: snapshot.backup?.oci_state || 'activation_pending',
      memory_used_percent: snapshot.resources?.memory_used_percent ?? null,
      disk_used_percent: snapshot.resources?.disk_used_percent ?? null,
      degraded_reasons: stale ? ['status_snapshot_stale', ...(snapshot.degraded_reasons || [])] : (snapshot.degraded_reasons || []),
    },
  };

  fs.mkdirSync(path.dirname(output), { recursive: true, mode: 0o750 });
  const tmp = `${output}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, `${JSON.stringify(row, null, 2)}\n`, { mode: 0o640 });
  fs.renameSync(tmp, output);
  console.log(`STATUS_ADAPTER=PASS state=${row.state} age_seconds=${row.source_age_seconds}`);
})().catch((error) => {
  console.error(`STATUS_ADAPTER=FAIL ${String(error.message || error).replace(/[\r\n]+/g, ' ')}`);
  process.exit(1);
});
