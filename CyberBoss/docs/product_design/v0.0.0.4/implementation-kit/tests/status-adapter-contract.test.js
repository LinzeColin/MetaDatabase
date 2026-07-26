'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const kit = path.resolve(__dirname, '..');
const adapterPath = path.join(kit, 'status/global-status-adapter.js');
const contract = JSON.parse(
  fs.readFileSync(path.join(kit, 'status/global-status-contract.fixture.json'), 'utf8'),
);
const { buildRow, sourceGenerationId } = require(adapterPath);

function snapshot(overrides = {}) {
  return {
    schema_version: '1.0',
    generation_id: '00000000-0000-4000-8000-000000000001',
    generated_at: '2026-07-26T00:00:00.000Z',
    service: {
      state: 'healthy',
      version: '0.0.0.4',
      source_commit: 'abc123',
      ...(overrides.service || {}),
    },
    wechat: { state: 'healthy' },
    runtime: { state: 'ready' },
    queue: { queued: 0 },
    canonical: { state: 'synced' },
    timeline: { build_state: 'ready' },
    backup: { r2_state: 'healthy', oci_state: 'activation_pending' },
    resources: {
      profile: 'tiny',
      memory_used_percent: 52,
      disk_used_percent: 60,
    },
    degraded_reasons: [],
    ...Object.fromEntries(
      Object.entries(overrides).filter(([key]) => key !== 'service'),
    ),
  };
}

function assertContract(row) {
  for (const field of contract.required_fields) {
    assert.ok(Object.hasOwn(row, field), `missing field ${field}`);
    const expected = contract.field_types[field];
    const actual = Array.isArray(row[field]) ? 'array' : typeof row[field];
    assert.equal(actual, expected, `type mismatch ${field}`);
  }
  assert.ok(contract.allowed_status_values.includes(row.status));
  assert.ok(row.parts.every((item) => contract.allowed_part_values.includes(item)));
  assert.ok(contract.allowed_agent_values.includes(row.agent));
}

test('healthy Access-protected snapshot matches the observed projects row contract', () => {
  const row = buildRow(snapshot(), {
    now: new Date('2026-07-26T00:00:30.000Z'),
    maxAgeSeconds: 120,
  });
  assertContract(row);
  assert.equal(row.status, 'access');
  assert.equal(row.version, '0.0.0.4');
  assert.equal(row.generation_id, '00000000-0000-4000-8000-000000000001');
  assert.equal(row.source_age_seconds, 30);
});

test('stale, stopped, activation-pending and unknown snapshots fail closed', () => {
  const cases = [
    [
      snapshot(),
      { now: new Date('2026-07-26T00:03:00.000Z'), maxAgeSeconds: 120 },
    ],
    [snapshot({ service: { state: 'stopped' } }), {
      now: new Date('2026-07-26T00:00:10.000Z'),
    }],
    [snapshot({ service: { state: 'activation_pending' } }), {
      now: new Date('2026-07-26T00:00:10.000Z'),
    }],
    [snapshot({ service: { state: 'invented' } }), {
      now: new Date('2026-07-26T00:00:10.000Z'),
    }],
  ];
  for (const [fixture, options] of cases) {
    const row = buildRow(fixture, options);
    assertContract(row);
    assert.equal(row.status, 'down');
  }
});

test('degraded service remains reachable but preserves degraded reasons', () => {
  const row = buildRow(
    snapshot({
      service: { state: 'degraded' },
      degraded_reasons: ['disk_pressure'],
    }),
    { now: new Date('2026-07-26T00:00:10.000Z') },
  );
  assert.equal(row.status, 'access');
  assert.deepEqual(row.details.degraded_reasons, ['disk_pressure']);
});

test('fallback generation id is deterministic and contains no source payload', () => {
  const fixture = snapshot();
  delete fixture.generation_id;
  const first = sourceGenerationId(fixture);
  const second = sourceGenerationId(fixture);
  assert.equal(first, second);
  assert.match(first, /^[0-9a-f]{24}$/);
});

test('row is free of forbidden secret, content and private-path patterns', () => {
  const serialized = JSON.stringify(
    buildRow(snapshot(), { now: new Date('2026-07-26T00:00:10.000Z') }),
  );
  const forbidden = [
    /authorization/i,
    /bearer/i,
    /context_token/i,
    /raw_prompt/i,
    /raw_result/i,
    /wxid_/i,
    /thread_id/i,
    /auth\.json/i,
    /\/root\//,
    /\/home\//,
    /\/etc\/cyberboss/,
  ];
  for (const pattern of forbidden) {
    assert.doesNotMatch(serialized, pattern);
  }
});

test('untrusted diagnostic fields are allowlisted and invalid freshness fails closed', () => {
  const fixture = snapshot({
    generation_id: 'raw_prompt_payload',
    generated_at: 'raw_prompt_payload',
    service: { version: 'raw_prompt_payload' },
    wechat: { state: 'raw_prompt_payload' },
    runtime: { state: 'raw_prompt_payload' },
    queue: { queued: 'raw_prompt_payload' },
    canonical: { state: 'raw_prompt_payload' },
    timeline: { build_state: 'raw_prompt_payload' },
    backup: {
      r2_state: 'raw_prompt_payload',
      oci_state: 'raw_prompt_payload',
    },
    resources: {
      profile: 'raw_prompt_payload',
      memory_used_percent: 101,
      disk_used_percent: -1,
    },
    degraded_reasons: ['raw_prompt_payload', 'disk_pressure'],
  });
  const row = buildRow(fixture, {
    now: new Date('2026-07-26T00:00:10.000Z'),
  });
  const serialized = JSON.stringify(row);
  assert.doesNotMatch(serialized, /raw_prompt_payload/);
  assert.equal(row.status, 'down');
  assert.equal(row.version, 'unknown');
  assert.equal(row.source_generated_at, null);
  assert.equal(row.details.queue, 0);
  assert.equal(row.details.memory_used_percent, null);
  assert.equal(row.details.disk_used_percent, null);
  assert.deepEqual(
    row.details.degraded_reasons,
    ['disk_pressure', 'status_snapshot_stale'],
  );
});

test('CLI atomically writes a contract-compatible row from a local fixture', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'cyberboss-status-contract-'));
  const source = path.join(root, 'snapshot.json');
  const output = path.join(root, 'row.json');
  const fixture = snapshot({ generated_at: new Date().toISOString() });
  fs.writeFileSync(source, `${JSON.stringify(fixture)}\n`);
  const result = spawnSync(process.execPath, [adapterPath], {
    env: {
      ...process.env,
      CB_STATUS_SOURCE_PATH: source,
      CB_GLOBAL_STATUS_OUTPUT: output,
      CB_STATUS_MAX_AGE_SECONDS: '120',
    },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /STATUS_ADAPTER=PASS/);
  const row = JSON.parse(fs.readFileSync(output, 'utf8'));
  assertContract(row);
  assert.equal(row.generation_id, fixture.generation_id);
  fs.rmSync(root, { recursive: true, force: true });
});
