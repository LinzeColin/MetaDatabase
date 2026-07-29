'use strict';
function stamp(ms) { return new Date(ms).toISOString(); }

class SqliteDeepSeekCircuitBreaker {
  constructor({ db, circuitKey = 'deepseek:deepseek-v4-pro', failureThreshold = 5, cooldownMs = 30_000, probeLeaseMs = 5 * 60_000, clock = () => Date.now() } = {}) {
    if (!db || typeof db.prepare !== 'function') throw new TypeError('db is required');
    this.db = db; this.key = circuitKey; this.failureThreshold = failureThreshold; this.cooldownMs = cooldownMs; this.probeLeaseMs = probeLeaseMs; this.clock = clock;
    db.exec(`CREATE TABLE IF NOT EXISTS shared_provider_circuit(
      circuit_key TEXT PRIMARY KEY,
      state TEXT NOT NULL CHECK(state IN ('closed','open','half_open')),
      consecutive_failures INTEGER NOT NULL DEFAULT 0,
      retry_at_ms INTEGER NOT NULL DEFAULT 0,
      probe_in_flight INTEGER NOT NULL DEFAULT 0 CHECK(probe_in_flight IN (0,1)),
      probe_expires_at_ms INTEGER NOT NULL DEFAULT 0,
      last_code TEXT,
      updated_at TEXT NOT NULL
    );`);
    db.prepare(`INSERT OR IGNORE INTO shared_provider_circuit(circuit_key,state,updated_at) VALUES(?,'closed',?)`).run(this.key, stamp(this.clock()));
  }
  _tx(fn) { this.db.exec('BEGIN IMMEDIATE'); try { const value = fn(); this.db.exec('COMMIT'); return value; } catch (error) { try { this.db.exec('ROLLBACK'); } catch {} throw error; } }
  _row() { return this.db.prepare('SELECT * FROM shared_provider_circuit WHERE circuit_key=?').get(this.key); }
  before() {
    return this._tx(() => {
      const now = this.clock(); const row = this._row();
      if (row.state === 'closed') return Object.freeze({ allowed: true });
      if (row.state === 'open' && now < Number(row.retry_at_ms)) return Object.freeze({ allowed: false, code: 'DEEPSEEK_CIRCUIT_OPEN' });
      if (row.state === 'half_open' && Number(row.probe_in_flight) === 1 && now < Number(row.probe_expires_at_ms)) return Object.freeze({ allowed: false, code: 'DEEPSEEK_CIRCUIT_PROBE_BUSY' });
      this.db.prepare(`UPDATE shared_provider_circuit SET state='half_open',probe_in_flight=1,probe_expires_at_ms=?,updated_at=? WHERE circuit_key=?`)
        .run(now + this.probeLeaseMs, stamp(now), this.key);
      return Object.freeze({ allowed: true, probe: true });
    });
  }
  success() {
    this.db.prepare(`UPDATE shared_provider_circuit SET state='closed',consecutive_failures=0,retry_at_ms=0,probe_in_flight=0,probe_expires_at_ms=0,last_code=NULL,updated_at=? WHERE circuit_key=?`)
      .run(stamp(this.clock()), this.key);
  }
  failure({ retryable = true, code = 'DEEPSEEK_REQUEST_FAILED' } = {}) {
    return this._tx(() => {
      const now = this.clock(); const row = this._row();
      if (!retryable) {
        this.db.prepare(`UPDATE shared_provider_circuit SET state='closed',probe_in_flight=0,probe_expires_at_ms=0,last_code=?,updated_at=? WHERE circuit_key=?`).run(code, stamp(now), this.key);
        return this.snapshot();
      }
      const failures = Number(row.consecutive_failures || 0) + 1;
      const open = failures >= this.failureThreshold || row.state === 'half_open';
      this.db.prepare(`UPDATE shared_provider_circuit SET state=?,consecutive_failures=?,retry_at_ms=?,probe_in_flight=0,probe_expires_at_ms=0,last_code=?,updated_at=? WHERE circuit_key=?`)
        .run(open ? 'open' : 'closed', failures, open ? now + this.cooldownMs : 0, code, stamp(now), this.key);
      return this.snapshot();
    });
  }
  snapshot() {
    const row = this._row();
    return Object.freeze({ state: row.state, consecutiveFailures: Number(row.consecutive_failures || 0), retryAt: Number(row.retry_at_ms || 0), probeInFlight: Boolean(row.probe_in_flight), probeExpiresAt: Number(row.probe_expires_at_ms || 0), lastCode: row.last_code || null });
  }
}
module.exports = { SqliteDeepSeekCircuitBreaker };
