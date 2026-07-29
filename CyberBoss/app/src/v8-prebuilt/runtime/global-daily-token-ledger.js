'use strict';
const crypto = require('node:crypto');
const { normalizeDeepSeekUsage, PRICE_NANOCNY_PER_TOKEN } = require('./deepseek-usage');

const GLOBAL_DAILY_TOKEN_CAP = 1_000_000_000;
function utcDay(ms) { return new Date(ms).toISOString().slice(0, 10); }

class GlobalDailyTokenLedger {
  constructor({ db, clock = () => Date.now(), reservationTtlMs = 10 * 60_000 } = {}) {
    if (!db || typeof db.prepare !== 'function') throw new TypeError('db is required');
    this.db = db; this.clock = clock; this.reservationTtlMs = reservationTtlMs;
    db.exec(`CREATE TABLE IF NOT EXISTS shared_token_daily(
      day_utc TEXT PRIMARY KEY,
      calls INTEGER NOT NULL DEFAULT 0,
      prompt_tokens INTEGER NOT NULL DEFAULT 0,
      cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
      cache_miss_tokens INTEGER NOT NULL DEFAULT 0,
      completion_tokens INTEGER NOT NULL DEFAULT 0,
      reasoning_tokens INTEGER NOT NULL DEFAULT 0,
      total_tokens INTEGER NOT NULL DEFAULT 0,
      fallback_charges INTEGER NOT NULL DEFAULT 0,
      estimated_cost_nanocny INTEGER NOT NULL DEFAULT 0,
      reservation_overrun_tokens INTEGER NOT NULL DEFAULT 0,
      accounting_integrity_violations INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS shared_token_reservations(
      reservation_id TEXT PRIMARY KEY,
      request_id TEXT NOT NULL UNIQUE,
      user_id TEXT NOT NULL,
      day_utc TEXT NOT NULL,
      reserved_tokens INTEGER NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('reserved','settled','released','expired_charged')),
      charged_tokens INTEGER,
      created_at_ms INTEGER NOT NULL,
      expires_at_ms INTEGER NOT NULL,
      settled_at_ms INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_shared_reservations_active
      ON shared_token_reservations(day_utc,state,expires_at_ms);`);
  }

  _tx(fn) { this.db.exec('BEGIN IMMEDIATE'); try { const value = fn(); this.db.exec('COMMIT'); return value; } catch (error) { try { this.db.exec('ROLLBACK'); } catch {} throw error; } }

  _charge(day, normalized, { fallback = 0, overrun = 0, integrityViolation = 0, now = this.clock() } = {}) {
    const usage = normalized || { promptTokens: 0, cacheHitTokens: 0, cacheMissTokens: 0, completionTokens: 0, reasoningTokens: 0, totalTokens: 0, estimatedCostNanoCny: 0 };
    this.db.prepare(`INSERT INTO shared_token_daily(
      day_utc,calls,prompt_tokens,cache_hit_tokens,cache_miss_tokens,completion_tokens,reasoning_tokens,total_tokens,
      fallback_charges,estimated_cost_nanocny,reservation_overrun_tokens,accounting_integrity_violations,updated_at
    ) VALUES(?,1,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(day_utc) DO UPDATE SET
      calls=calls+1,prompt_tokens=prompt_tokens+excluded.prompt_tokens,
      cache_hit_tokens=cache_hit_tokens+excluded.cache_hit_tokens,cache_miss_tokens=cache_miss_tokens+excluded.cache_miss_tokens,
      completion_tokens=completion_tokens+excluded.completion_tokens,reasoning_tokens=reasoning_tokens+excluded.reasoning_tokens,
      total_tokens=total_tokens+excluded.total_tokens,fallback_charges=fallback_charges+excluded.fallback_charges,
      estimated_cost_nanocny=estimated_cost_nanocny+excluded.estimated_cost_nanocny,
      reservation_overrun_tokens=reservation_overrun_tokens+excluded.reservation_overrun_tokens,
      accounting_integrity_violations=accounting_integrity_violations+excluded.accounting_integrity_violations,
      updated_at=excluded.updated_at`).run(
      day, usage.promptTokens, usage.cacheHitTokens, usage.cacheMissTokens, usage.completionTokens,
      usage.reasoningTokens, usage.totalTokens, fallback, usage.estimatedCostNanoCny,
      overrun, integrityViolation, new Date(now).toISOString(),
    );
  }

  _expire(now) {
    const rows = this.db.prepare("SELECT * FROM shared_token_reservations WHERE state='reserved' AND expires_at_ms<=?").all(now);
    for (const row of rows) {
      const result = this.db.prepare("UPDATE shared_token_reservations SET state='expired_charged',charged_tokens=reserved_tokens,settled_at_ms=? WHERE reservation_id=? AND state='reserved'")
        .run(now, row.reservation_id);
      if (result.changes === 1) {
        const total = Number(row.reserved_tokens);
        this._charge(row.day_utc, {
          promptTokens: 0, cacheHitTokens: 0, cacheMissTokens: 0, completionTokens: 0, reasoningTokens: 0,
          totalTokens: total, estimatedCostNanoCny: total * PRICE_NANOCNY_PER_TOKEN.output,
        }, { fallback: 1, now });
      }
    }
  }

  _totals(day) {
    const used = Number(this.db.prepare('SELECT total_tokens AS n FROM shared_token_daily WHERE day_utc=?').get(day)?.n || 0);
    const reserved = Number(this.db.prepare("SELECT COALESCE(SUM(reserved_tokens),0) AS n FROM shared_token_reservations WHERE day_utc=? AND state='reserved'").get(day).n || 0);
    return { used, reserved };
  }

  totals(now = this.clock()) {
    return this._tx(() => {
      this._expire(now); const day = utcDay(now); const { used, reserved } = this._totals(day);
      return Object.freeze({ day, usedTokens: used, reservedTokens: reserved, remainingTokens: Math.max(0, GLOBAL_DAILY_TOKEN_CAP - used - reserved), capTokens: GLOBAL_DAILY_TOKEN_CAP });
    });
  }

  reserve({ requestId, userId, estimatedTotalTokens, now = this.clock() }) {
    if (!requestId || !userId || !Number.isSafeInteger(estimatedTotalTokens) || estimatedTotalTokens < 0 || estimatedTotalTokens > GLOBAL_DAILY_TOKEN_CAP) throw new TypeError('invalid reservation');
    return this._tx(() => {
      this._expire(now); const day = utcDay(now);
      const existing = this.db.prepare('SELECT * FROM shared_token_reservations WHERE request_id=?').get(requestId);
      if (existing) {
        if (existing.user_id !== userId) return Object.freeze({ accepted: false, code: 'REQUEST_IDENTITY_CONFLICT', providerCalls: 0 });
        if (existing.state === 'reserved') return Object.freeze({ accepted: true, existing: true, reservationId: existing.reservation_id, reservedTokens: Number(existing.reserved_tokens), day });
        if (['settled', 'expired_charged'].includes(existing.state)) return Object.freeze({ accepted: false, code: 'REQUEST_ALREADY_ACCOUNTED', providerCalls: 0, chargedTokens: Number(existing.charged_tokens || 0) });
      }
      const { used, reserved } = this._totals(day);
      if (used + reserved + estimatedTotalTokens > GLOBAL_DAILY_TOKEN_CAP) return Object.freeze({ accepted: false, code: 'GLOBAL_DAILY_TOKEN_CAP', providerCalls: 0, day, usedTokens: used, reservedTokens: reserved, capTokens: GLOBAL_DAILY_TOKEN_CAP });
      if (existing?.state === 'released') {
        this.db.prepare(`UPDATE shared_token_reservations SET day_utc=?,reserved_tokens=?,state='reserved',charged_tokens=NULL,created_at_ms=?,expires_at_ms=?,settled_at_ms=NULL WHERE reservation_id=? AND state='released'`)
          .run(day, estimatedTotalTokens, now, now + this.reservationTtlMs, existing.reservation_id);
        return Object.freeze({ accepted: true, reservationId: existing.reservation_id, reservedTokens: estimatedTotalTokens, day, reusedReleased: true });
      }
      const reservationId = `rsv_${crypto.randomUUID()}`;
      this.db.prepare(`INSERT INTO shared_token_reservations(reservation_id,request_id,user_id,day_utc,reserved_tokens,state,charged_tokens,created_at_ms,expires_at_ms,settled_at_ms)
        VALUES(?,?,?,?,?,'reserved',NULL,?,?,NULL)`).run(reservationId, requestId, userId, day, estimatedTotalTokens, now, now + this.reservationTtlMs);
      return Object.freeze({ accepted: true, reservationId, reservedTokens: estimatedTotalTokens, day });
    });
  }

  settle({ reservationId, usage, now = this.clock() }) {
    return this._tx(() => {
      const row = this.db.prepare('SELECT * FROM shared_token_reservations WHERE reservation_id=?').get(reservationId);
      if (!row) throw Object.assign(new Error('RESERVATION_NOT_FOUND'), { code: 'RESERVATION_NOT_FOUND' });
      if (['settled', 'expired_charged'].includes(row.state)) return Object.freeze({ totalTokens: Number(row.charged_tokens || 0), idempotent: true });
      if (row.state !== 'reserved') throw Object.assign(new Error('RESERVATION_NOT_ACTIVE'), { code: 'RESERVATION_NOT_ACTIVE' });
      const normalized = normalizeDeepSeekUsage(usage);
      const charged = normalized || {
        promptTokens: 0, cacheHitTokens: 0, cacheMissTokens: 0, completionTokens: 0, reasoningTokens: 0,
        totalTokens: Number(row.reserved_tokens), estimatedCostNanoCny: Number(row.reserved_tokens) * PRICE_NANOCNY_PER_TOKEN.output,
      };
      const overrun = Math.max(0, charged.totalTokens - Number(row.reserved_tokens));
      this.db.prepare("UPDATE shared_token_reservations SET state='settled',charged_tokens=?,settled_at_ms=? WHERE reservation_id=? AND state='reserved'")
        .run(charged.totalTokens, now, reservationId);
      this._charge(row.day_utc, charged, { fallback: normalized ? 0 : 1, overrun, integrityViolation: overrun > 0 ? 1 : 0, now });
      return Object.freeze({ ...charged, usageReported: Boolean(normalized), reservationOverrunTokens: overrun, accountingIntegrityViolation: overrun > 0 });
    });
  }

  release(reservationId, now = this.clock()) {
    return this.db.prepare("UPDATE shared_token_reservations SET state='released',settled_at_ms=? WHERE reservation_id=? AND state='reserved'").run(now, reservationId).changes === 1;
  }

  status(now = this.clock()) {
    const base = this.totals(now); const row = this.db.prepare('SELECT * FROM shared_token_daily WHERE day_utc=?').get(base.day) || {};
    const estimatedCostNanoCny = Number(row.estimated_cost_nanocny || 0);
    return Object.freeze({
      ...base,
      calls: Number(row.calls || 0),
      promptTokens: Number(row.prompt_tokens || 0),
      cacheHitTokens: Number(row.cache_hit_tokens || 0),
      cacheMissTokens: Number(row.cache_miss_tokens || 0),
      completionTokens: Number(row.completion_tokens || 0),
      reasoningTokens: Number(row.reasoning_tokens || 0),
      fallbackCharges: Number(row.fallback_charges || 0),
      estimatedCostNanoCny,
      estimatedCostCny: estimatedCostNanoCny / 1_000_000_000,
      reservationOverrunTokens: Number(row.reservation_overrun_tokens || 0),
      accountingIntegrityViolations: Number(row.accounting_integrity_violations || 0),
    });
  }
}

module.exports = { GlobalDailyTokenLedger, GLOBAL_DAILY_TOKEN_CAP, utcDay };
