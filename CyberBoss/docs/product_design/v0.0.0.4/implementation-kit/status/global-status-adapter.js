#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');

const defaultSourcePath = '/var/lib/cyberboss/status/snapshot.json';
const defaultOutput = '/var/lib/cyberboss/status/global-project-row.json';
const generationIdPattern = /^(?:[0-9a-f]{24}|[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/i;
const allowedReasons = new Set([
  'disk_pressure',
  'memory_pressure',
  'status_snapshot_stale',
  'wechat_poll_not_verified',
  'wechat_poll_stale',
]);

function enumValue(value, allowed, fallback = 'unknown') {
  return typeof value === 'string' && allowed.includes(value) ? value : fallback;
}

function nonNegativeInteger(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : 0;
}

function percentOrNull(value) {
  return Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
}

function isoOrNull(value) {
  if (typeof value !== 'string') return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function sourceGenerationId(snapshot) {
  if (
    typeof snapshot.generation_id === 'string' &&
    generationIdPattern.test(snapshot.generation_id)
  ) {
    return snapshot.generation_id;
  }
  return createHash('sha256')
    .update([
      snapshot.generated_at || 'missing',
      snapshot.service?.version || 'unknown',
      snapshot.service?.source_commit || 'unknown',
    ].join('|'))
    .digest('hex')
    .slice(0, 24);
}

function buildRow(snapshot, options = {}) {
  const source = snapshot && typeof snapshot === 'object' ? snapshot : {};
  const now = options.now instanceof Date ? options.now : new Date();
  const configuredMaxAge = Number(options.maxAgeSeconds ?? 120);
  const maxAgeSeconds = Number.isFinite(configuredMaxAge) &&
    configuredMaxAge >= 1 &&
    configuredMaxAge <= 3600
    ? configuredMaxAge
    : 120;
  const sourceGeneratedAt = isoOrNull(source.generated_at);
  const generated = sourceGeneratedAt ? new Date(sourceGeneratedAt) : null;
  const tooFarInFuture = generated && generated.getTime() > now.getTime() + 60_000;
  const age = !generated || tooFarInFuture
    ? Infinity
    : Math.max(0, (now.getTime() - generated.getTime()) / 1000);
  const stale = age > maxAgeSeconds;
  const serviceState = [
    'healthy',
    'degraded',
    'stopped',
    'activation_pending',
    'not_verified',
  ].includes(source.service?.state)
    ? source.service.state
    : 'not_verified';

  // The current public page contract accepts only run/access/down. CyberBoss is
  // Access-protected, so healthy/degraded maps to access; unsafe/unverified/stale
  // never defaults to a green-looking row.
  const status = !stale && ['healthy', 'degraded'].includes(serviceState)
    ? 'access'
    : 'down';
  const degradedReasons = stale
    ? ['status_snapshot_stale', ...(source.degraded_reasons || [])]
    : (source.degraded_reasons || []);
  const safeReasons = [...new Set(degradedReasons)]
    .filter((reason) => allowedReasons.has(reason))
    .sort();

  return {
    schema_version: 1,
    name: 'CyberBoss Cloud',
    url: 'https://cyberboss.linzezhang.com',
    parts: ['前台', '后台'],
    host: 'OVH Singapore VPS-1',
    db: 'Private-MetaDatabase + SQLite spool',
    store: 'R2 + OCI',
    deploy: 'systemd immutable release',
    backup: 'R2 snapshots → OCI selected copy',
    agent: '中',
    notify: '无',
    status,
    version: typeof source.service?.version === 'string' &&
      /^\d+\.\d+\.\d+(?:\.\d+)?$/.test(source.service.version)
      ? source.service.version
      : 'unknown',
    generation_id: sourceGenerationId(source),
    source_generated_at: sourceGeneratedAt,
    source_age_seconds: Number.isFinite(age) ? Math.round(age) : null,
    activation_state: serviceState,
    details: {
      resource_profile: enumValue(
        source.resources?.profile,
        ['constrained', 'tiny', 'standard', 'unselected'],
        'unselected',
      ),
      wechat: enumValue(
        source.wechat?.state,
        ['healthy', 'degraded', 'stopped', 'activation_pending', 'not_verified', 'unknown'],
      ),
      runtime: enumValue(
        source.runtime?.state,
        ['ready', 'running', 'busy', 'degraded', 'stopped', 'activation_pending', 'not_verified', 'unknown'],
      ),
      queue: nonNegativeInteger(source.queue?.queued),
      canonical: enumValue(
        source.canonical?.state,
        ['synced', 'sync_pending', 'degraded', 'failed', 'activation_pending', 'not_verified', 'unknown'],
      ),
      timeline: enumValue(
        source.timeline?.build_state,
        ['ready', 'building', 'degraded', 'failed', 'activation_pending', 'not_verified', 'unknown'],
      ),
      r2: enumValue(
        source.backup?.r2_state,
        ['healthy', 'degraded', 'failed', 'not_configured', 'activation_pending', 'not_verified', 'unknown'],
        'activation_pending',
      ),
      oci: enumValue(
        source.backup?.oci_state,
        ['healthy', 'degraded', 'failed', 'not_configured', 'activation_pending', 'not_verified', 'unknown'],
        'activation_pending',
      ),
      memory_used_percent: percentOrNull(source.resources?.memory_used_percent),
      disk_used_percent: percentOrNull(source.resources?.disk_used_percent),
      degraded_reasons: safeReasons,
    },
  };
}

async function loadSnapshot({ sourcePath, sourceUrl }) {
  if (fs.existsSync(sourcePath)) {
    return JSON.parse(fs.readFileSync(sourcePath, 'utf8'));
  }
  if (!sourceUrl) {
    throw new Error('local snapshot missing and CB_STATUS_SOURCE_URL unset');
  }
  const clientId = process.env.CF_ACCESS_CLIENT_ID;
  const clientSecret = process.env.CF_ACCESS_CLIENT_SECRET;
  if (!clientId || !clientSecret) {
    throw new Error('remote snapshot requires Cloudflare Access service token');
  }
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

async function main() {
  const sourcePath = process.env.CB_STATUS_SOURCE_PATH || defaultSourcePath;
  const sourceUrl = process.env.CB_STATUS_SOURCE_URL || '';
  const output = process.env.CB_GLOBAL_STATUS_OUTPUT || defaultOutput;
  const maxAgeSeconds = Number(process.env.CB_STATUS_MAX_AGE_SECONDS || 120);
  const snapshot = await loadSnapshot({ sourcePath, sourceUrl });
  const row = buildRow(snapshot, { maxAgeSeconds });

  fs.mkdirSync(path.dirname(output), { recursive: true, mode: 0o750 });
  const temp = `${output}.tmp-${process.pid}`;
  fs.writeFileSync(temp, `${JSON.stringify(row, null, 2)}\n`, { mode: 0o640 });
  fs.renameSync(temp, output);
  console.log(
    `STATUS_ADAPTER=PASS status=${row.status} ` +
    `version=${row.version} generation_id=${row.generation_id}`,
  );
}

if (require.main === module) {
  main().catch((error) => {
    console.error(
      `STATUS_ADAPTER=FAIL ${String(error.message || error).replace(/[\r\n]+/g, ' ')}`,
    );
    process.exit(1);
  });
}

module.exports = { buildRow, loadSnapshot, sourceGenerationId };
