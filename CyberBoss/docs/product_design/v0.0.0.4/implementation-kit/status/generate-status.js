#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { execFileSync } = require('node:child_process');

const db = process.env.CB_RUNTIME_DB || '/var/lib/cyberboss/runtime.db';
const output = process.env.CB_STATUS_PATH || '/var/lib/cyberboss/status/snapshot.json';
const appRoot = process.env.CB_APP_ROOT || '/opt/cyberboss-cloud';
const now = new Date();

function scalar(sql, fallback = null) {
  try {
    const value = execFileSync('sqlite3', ['-noheader', db, sql], { encoding: 'utf8', timeout: 5000 }).trim();
    return value === '' ? fallback : value;
  } catch {
    return fallback;
  }
}

function number(sql, fallback = 0) {
  const x = Number(scalar(sql, fallback));
  return Number.isFinite(x) ? x : fallback;
}

function stateValue(key, fallback = null) {
  const raw = scalar(`SELECT value_redacted_json FROM service_state WHERE key='${key.replaceAll("'", "''")}' LIMIT 1;`, null);
  if (raw == null) return fallback;
  try {
    const value = JSON.parse(raw);
    return typeof value === 'object' && value !== null && Object.hasOwn(value, 'value') ? value.value : value;
  } catch {
    return fallback;
  }
}

function isoOrNull(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function ageSeconds(value) {
  const iso = isoOrNull(value);
  if (!iso) return null;
  return Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 1000));
}

function releaseCommit() {
  try {
    const manifest = JSON.parse(fs.readFileSync(path.join(appRoot, 'current', 'release-manifest.json'), 'utf8'));
    return typeof manifest.commit === 'string' ? manifest.commit.slice(0, 12) : 'unknown';
  } catch {
    return 'unknown';
  }
}

function diskStats() {
  try {
    const line = execFileSync('df', ['-Pk', '/'], { encoding: 'utf8', timeout: 3000 }).trim().split('\n').at(-1).trim().split(/\s+/);
    return Number(line[4].replace('%', '')) || 0;
  } catch { return 0; }
}

function inodeStats() {
  try {
    const line = execFileSync('df', ['-Pik', '/'], { encoding: 'utf8', timeout: 3000 }).trim().split('\n').at(-1).trim().split(/\s+/);
    return Number(line[4].replace('%', '')) || 0;
  } catch { return 0; }
}

function memoryUsedPercent() {
  const total = os.totalmem();
  return total > 0 ? Number((((total - os.freemem()) / total) * 100).toFixed(1)) : 0;
}

function swapUsedPercent() {
  try {
    const text = fs.readFileSync('/proc/meminfo', 'utf8');
    const total = Number(text.match(/^SwapTotal:\s+(\d+)/m)?.[1] || 0);
    const free = Number(text.match(/^SwapFree:\s+(\d+)/m)?.[1] || 0);
    return total > 0 ? Number((((total - free) / total) * 100).toFixed(1)) : 0;
  } catch { return 0; }
}

const pollAt = stateValue('wechat.last_poll_success_at');
const sendAt = stateValue('wechat.last_outbound_confirmed_at');
const runtimeAt = stateValue('runtime.last_success_at');
const canonicalAt = stateValue('canonical.last_verified_at');
const timelineBuildAt = stateValue('timeline.last_build_at');
const r2At = stateValue('backup.r2_last_snapshot_at');
const restoreAt = stateValue('backup.last_restore_drill_at');
const selfHealAt = stateValue('self_heal.last_run_at');

const disk = diskStats();
const memory = memoryUsedPercent();
const pollAge = ageSeconds(pollAt);
const degraded = [];
if (disk >= Number(process.env.CB_DEGRADED_DISK_PERCENT || 85)) degraded.push('disk_pressure');
if (memory >= Number(process.env.CB_DEGRADED_MEMORY_PERCENT || 85)) degraded.push('memory_pressure');
if (pollAge == null) degraded.push('wechat_poll_not_verified');
else if (pollAge > 90) degraded.push('wechat_poll_stale');

const running = number("SELECT COUNT(*) FROM jobs WHERE status='running';");
const queued = number("SELECT COUNT(*) FROM jobs WHERE status IN ('received','queued','failed_retryable');");
const waitingApproval = number("SELECT COUNT(*) FROM jobs WHERE status='waiting_approval';");
const outboxPending = number("SELECT COUNT(*) FROM outbox_messages WHERE status IN ('pending','sending','retry');");
const outboxFailed = number("SELECT COUNT(*) FROM outbox_messages WHERE status='failed_terminal';");
const syncPending = number("SELECT COUNT(*) FROM sync_spool WHERE status IN ('pending','syncing','retry');");

const snapshot = {
  schema_version: '1.0',
  generation_id: randomUUID(),
  generated_at: now.toISOString(),
  service: {
    name: 'cyberboss-cloud',
    state: degraded.length ? 'degraded' : 'healthy',
    version: process.env.CB_PRODUCT_VERSION || '0.0.0.4',
    source_commit: releaseCommit(),
    deployment: 'ovh-singapore',
    uptime_seconds: Math.floor(os.uptime()),
  },
  wechat: {
    state: pollAge != null && pollAge <= 90 ? (outboxFailed ? 'degraded' : 'healthy') : 'unknown',
    last_poll_success_at: isoOrNull(pollAt),
    poll_age_seconds: pollAge,
    last_inbound_at: isoOrNull(stateValue('wechat.last_inbound_at')),
    last_outbound_confirmed_at: isoOrNull(sendAt),
    outbox_pending: outboxPending,
    outbox_failed: outboxFailed,
  },
  runtime: {
    selected: process.env.CYBERBOSS_RUNTIME || 'codex',
    state: stateValue('runtime.state', 'unknown'),
    auth_state: stateValue('runtime.auth_state', 'unknown'),
    active_job: running > 0,
    active_job_age_seconds: number("SELECT COALESCE(CAST((julianday('now')-julianday(MIN(started_at)))*86400 AS INTEGER),0) FROM jobs WHERE status='running';"),
    last_success_at: isoOrNull(runtimeAt),
  },
  queue: {
    queued,
    running,
    waiting_approval: waitingApproval,
    oldest_age_seconds: number("SELECT COALESCE(CAST((julianday('now')-julianday(MIN(created_at)))*86400 AS INTEGER),0) FROM jobs WHERE status IN ('received','queued','failed_retryable');"),
  },
  canonical: {
    state: syncPending ? 'sync_pending' : stateValue('canonical.state', 'unknown'),
    last_object_sha256: stateValue('canonical.last_object_sha256', null),
    last_verified_at: isoOrNull(canonicalAt),
    pending_events: syncPending,
    oldest_pending_age_seconds: number("SELECT COALESCE(CAST((julianday('now')-julianday(MIN(created_at)))*86400 AS INTEGER),0) FROM sync_spool WHERE status IN ('pending','syncing','retry');"),
  },
  timeline: {
    last_write_at: isoOrNull(stateValue('timeline.last_write_at')),
    last_build_at: isoOrNull(timelineBuildAt),
    entry_count: number("SELECT COUNT(*) FROM job_events WHERE event_type LIKE 'timeline.%';"),
    build_state: stateValue('timeline.build_state', 'unknown'),
  },
  backup: {
    r2_state: stateValue('backup.r2_state', r2At ? 'healthy' : 'unknown'),
    r2_last_snapshot_at: isoOrNull(r2At),
    oci_state: process.env.CB_OCI_STATE || 'activation_pending',
    oci_last_backup_at: isoOrNull(stateValue('backup.oci_last_backup_at')),
    last_restore_drill_at: isoOrNull(restoreAt),
  },
  resources: {
    profile: process.env.CB_RESOURCE_PROFILE || 'unselected',
    cpu_load_1m: Number(os.loadavg()[0].toFixed(2)),
    memory_used_percent: memory,
    swap_used_percent: swapUsedPercent(),
    disk_used_percent: disk,
    inode_used_percent: inodeStats(),
  },
  self_heal: {
    last_run_at: isoOrNull(selfHealAt),
    last_action: stateValue('self_heal.last_action', 'none'),
    last_result: stateValue('self_heal.last_result', 'unknown'),
  },
  degraded_reasons: degraded,
};

const serialized = `${JSON.stringify(snapshot, null, 2)}\n`;
const forbidden = [
  /authorization/i, /bearer/i, /context_token/i, /raw_prompt/i, /raw_result/i,
  /wxid_/i, /auth\.json/i, /\/root\//, /\/home\//, /\/etc\/cyberboss/,
];
for (const pattern of forbidden) {
  if (pattern.test(serialized)) throw new Error(`forbidden status pattern: ${pattern}`);
}

fs.mkdirSync(path.dirname(output), { recursive: true, mode: 0o750 });
const temp = `${output}.tmp-${process.pid}`;
fs.writeFileSync(temp, serialized, { mode: 0o640 });
fs.renameSync(temp, output);
console.log(`STATUS=PASS path=${output} state=${snapshot.service.state}`);
