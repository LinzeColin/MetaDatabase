"use strict";

// CB-700 / AC-045, AC-046: the durable token ledger over model_budget_reservations
// and model_token_usage_daily.
//
// The limit check and the reservation insert happen inside one BEGIN IMMEDIATE
// transaction, so two concurrent requests can never both pass a check that only
// one of them fits under. request_id is unique per user, so a retried inbound
// message cannot double-charge, and the uniqueness is scoped to the user so two
// users choosing the same request id never collide.

class ModelBudgetStoreError extends Error {
  constructor(code) {
    super(code);
    this.name = "ModelBudgetStoreError";
    this.code = code;
  }
}

function utcKeys(epochMs) {
  const date = new Date(epochMs);
  if (!Number.isFinite(date.getTime())) {
    throw new ModelBudgetStoreError("CLOCK_INVALID");
  }
  const iso = date.toISOString();
  return { day: iso.slice(0, 10), month: iso.slice(0, 7) };
}

function iso(epochMs) {
  const date = new Date(epochMs);
  if (!Number.isFinite(date.getTime())) {
    throw new ModelBudgetStoreError("CLOCK_INVALID");
  }
  return date.toISOString();
}

function runTransaction(database, body) {
  database.exec("BEGIN IMMEDIATE");
  try {
    const result = body();
    database.exec("COMMIT");
    return result;
  } catch (error) {
    try {
      database.exec("ROLLBACK");
    } catch {
      // A commit may already have completed; the original error is preserved.
    }
    throw error;
  }
}

class SqliteModelBudgetLedger {
  constructor({ database, clock = () => Date.now(), reservationTtlMs = 10 * 60 * 1000 } = {}) {
    if (!database || typeof database.prepare !== "function") {
      throw new ModelBudgetStoreError("DATABASE_REQUIRED");
    }
    if (!Number.isSafeInteger(reservationTtlMs) || reservationTtlMs < 1) {
      throw new ModelBudgetStoreError("RESERVATION_TTL_INVALID");
    }
    this.database = database;
    this.clock = clock;
    this.reservationTtlMs = reservationTtlMs;
  }

  #scope({ userId = null, providerId = null } = {}) {
    const parts = [];
    const values = [];
    if (userId) {
      parts.push("user_id = ?");
      values.push(userId);
    }
    if (providerId) {
      parts.push("provider_id = ?");
      values.push(providerId);
    }
    return { sql: parts.length ? ` AND ${parts.join(" AND ")}` : "", values };
  }

  #upsertUsage({ userId, providerId, day, inputTokens, outputTokens, totalTokens, usageReported, epochMs }) {
    this.database
      .prepare(
        `INSERT INTO model_token_usage_daily(
           user_id, provider_id, day, calls, input_tokens, output_tokens,
           total_tokens, fallback_usage_records, updated_at
         ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
         ON CONFLICT(user_id, provider_id, day) DO UPDATE SET
           calls = calls + excluded.calls,
           input_tokens = input_tokens + excluded.input_tokens,
           output_tokens = output_tokens + excluded.output_tokens,
           total_tokens = total_tokens + excluded.total_tokens,
           fallback_usage_records =
             fallback_usage_records + excluded.fallback_usage_records,
           updated_at = excluded.updated_at`,
      )
      .run(
        userId,
        providerId,
        day,
        Number.isInteger(inputTokens) ? inputTokens : 0,
        Number.isInteger(outputTokens) ? outputTokens : 0,
        totalTokens,
        usageReported ? 0 : 1,
        iso(epochMs),
      );
  }

  // AC-046: a reservation whose process crashed before settlement is charged at
  // its full reserved amount. Under-charging after a crash would let a restart
  // loop spend without bound.
  expireReservations({ epochMs = this.clock() } = {}) {
    const nowIso = iso(epochMs);
    return runTransaction(this.database, () => {
      const rows = this.database
        .prepare(
          `SELECT reservation_id, request_id, user_id, provider_id,
                  reserved_tokens, created_at
           FROM model_budget_reservations
           WHERE state='reserved' AND expires_at <= ?
           ORDER BY created_at, reservation_id`,
        )
        .all(nowIso);
      const update = this.database.prepare(
        `UPDATE model_budget_reservations
         SET state='expired_charged', charged_tokens=reserved_tokens,
             input_tokens=NULL, output_tokens=NULL, usage_reported=0,
             charge_mode='reservation_fallback',
             reason_code='RESERVATION_EXPIRED', settled_at=?
         WHERE reservation_id=? AND state='reserved'`,
      );
      let charged = 0;
      for (const row of rows) {
        if (Number(update.run(nowIso, row.reservation_id).changes) !== 1) {
          continue;
        }
        const { day } = utcKeys(Date.parse(row.created_at));
        this.#upsertUsage({
          userId: row.user_id,
          providerId: row.provider_id,
          day,
          inputTokens: null,
          outputTokens: null,
          totalTokens: Number(row.reserved_tokens),
          usageReported: false,
          epochMs,
        });
        charged += 1;
      }
      return charged;
    });
  }

  totals({ userId = null, providerId = null, includeReservations = true, epochMs = this.clock() } = {}) {
    this.expireReservations({ epochMs });
    const { day, month } = utcKeys(epochMs);
    const scope = this.#scope({ userId, providerId });
    const daily = this.database
      .prepare(
        `SELECT COALESCE(SUM(total_tokens),0) AS used, COALESCE(SUM(calls),0) AS calls
         FROM model_token_usage_daily WHERE day = ?${scope.sql}`,
      )
      .get(day, ...scope.values);
    const monthly = this.database
      .prepare(
        `SELECT COALESCE(SUM(total_tokens),0) AS used, COALESCE(SUM(calls),0) AS calls
         FROM model_token_usage_daily WHERE substr(day,1,7) = ?${scope.sql}`,
      )
      .get(month, ...scope.values);
    let dailyReservedTokens = 0;
    let monthlyReservedTokens = 0;
    if (includeReservations) {
      const nowIso = iso(epochMs);
      dailyReservedTokens = Number(
        this.database
          .prepare(
            `SELECT COALESCE(SUM(reserved_tokens),0) AS reserved
             FROM model_budget_reservations
             WHERE state='reserved' AND expires_at > ?
               AND substr(created_at,1,10)=?${scope.sql}`,
          )
          .get(nowIso, day, ...scope.values).reserved || 0,
      );
      monthlyReservedTokens = Number(
        this.database
          .prepare(
            `SELECT COALESCE(SUM(reserved_tokens),0) AS reserved
             FROM model_budget_reservations
             WHERE state='reserved' AND expires_at > ?
               AND substr(created_at,1,7)=?${scope.sql}`,
          )
          .get(nowIso, month, ...scope.values).reserved || 0,
      );
    }
    return Object.freeze({
      day,
      month,
      dailyUsedTokens: Number(daily.used || 0),
      monthlyUsedTokens: Number(monthly.used || 0),
      dailyReservedTokens,
      monthlyReservedTokens,
      callsToday: Number(daily.calls || 0),
      callsMonth: Number(monthly.calls || 0),
    });
  }

  findReservationByRequest({ userId, requestId }) {
    const row = this.database
      .prepare(
        `SELECT reservation_id AS reservationId, request_id AS requestId,
                user_id AS userId, provider_id AS providerId,
                reserved_tokens AS reservedTokens, state,
                created_at AS createdAt, expires_at AS expiresAt,
                charged_tokens AS chargedTokens
         FROM model_budget_reservations
         WHERE user_id=? AND request_id=?`,
      )
      .get(userId, requestId);
    return row ? Object.freeze({ ...row }) : null;
  }

  // The whole point of this method: check and reserve atomically.
  reserveIfWithinLimits({ reservationId, requestId, userId, providerId, reservedTokens, limits, epochMs = this.clock() }) {
    this.expireReservations({ epochMs });
    const createdAt = iso(epochMs);
    const expiresAt = iso(epochMs + this.reservationTtlMs);
    const { day, month } = utcKeys(epochMs);
    return runTransaction(this.database, () => {
      const existing = this.database
        .prepare(
          "SELECT state FROM model_budget_reservations WHERE user_id=? AND request_id=?",
        )
        .get(userId, requestId);
      if (existing) {
        return Object.freeze({
          allowed: false,
          code: "DUPLICATE_MODEL_REQUEST",
          modelCalls: 0,
          existingState: existing.state,
        });
      }
      const used = ({ scopedUserId = null, period }) => {
        const clause = scopedUserId ? " AND user_id=?" : "";
        const values = period === "day" ? [day] : [month];
        if (scopedUserId) {
          values.push(scopedUserId);
        }
        return Number(
          this.database
            .prepare(
              `SELECT COALESCE(SUM(total_tokens),0) AS value
               FROM model_token_usage_daily
               WHERE ${period === "day" ? "day=?" : "substr(day,1,7)=?"}${clause}`,
            )
            .get(...values).value || 0,
        );
      };
      const reserved = ({ scopedUserId = null, period }) => {
        const clause = scopedUserId ? " AND user_id=?" : "";
        const values = period === "day" ? [day] : [month];
        if (scopedUserId) {
          values.push(scopedUserId);
        }
        return Number(
          this.database
            .prepare(
              `SELECT COALESCE(SUM(reserved_tokens),0) AS value
               FROM model_budget_reservations
               WHERE state='reserved' AND ${
                 period === "day"
                   ? "substr(created_at,1,10)=?"
                   : "substr(created_at,1,7)=?"
               }${clause}`,
            )
            .get(...values).value || 0,
        );
      };
      const checks = [
        [
          "USER_DAILY_TOKEN_BUDGET_EXHAUSTED",
          used({ scopedUserId: userId, period: "day" }) +
            reserved({ scopedUserId: userId, period: "day" }) +
            reservedTokens,
          limits.perUserDailyTokens,
        ],
        [
          "USER_MONTHLY_TOKEN_BUDGET_EXHAUSTED",
          used({ scopedUserId: userId, period: "month" }) +
            reserved({ scopedUserId: userId, period: "month" }) +
            reservedTokens,
          limits.perUserMonthlyTokens,
        ],
        [
          "GLOBAL_DAILY_TOKEN_BUDGET_EXHAUSTED",
          used({ period: "day" }) + reserved({ period: "day" }) + reservedTokens,
          limits.globalDailyTokens,
        ],
        [
          "GLOBAL_MONTHLY_TOKEN_BUDGET_EXHAUSTED",
          used({ period: "month" }) + reserved({ period: "month" }) + reservedTokens,
          limits.globalMonthlyTokens,
        ],
      ];
      const blocked = checks.find(([, projected, limit]) => projected > limit);
      if (blocked) {
        return Object.freeze({
          allowed: false,
          code: blocked[0],
          modelCalls: 0,
          reservedTokens,
          projectedTokens: blocked[1],
          limit: blocked[2],
        });
      }
      this.database
        .prepare(
          `INSERT INTO model_budget_reservations(
             reservation_id, request_id, user_id, provider_id, reserved_tokens,
             state, created_at, expires_at
           ) VALUES (?, ?, ?, ?, ?, 'reserved', ?, ?)`,
        )
        .run(reservationId, requestId, userId, providerId, reservedTokens, createdAt, expiresAt);
      return Object.freeze({
        allowed: true,
        code: "OK",
        reservationId,
        requestId,
        userId,
        providerId,
        reservedTokens,
        createdAt,
        expiresAt,
        state: "reserved",
        utilizationRatio: Math.max(
          ...checks.map(([, projected, limit]) => Math.min(1, projected / limit)),
        ),
        modelCalls: 0,
      });
    });
  }

  settle({ reservationId, inputTokens, outputTokens, totalTokens, usageReported, chargeMode = "actual", epochMs = this.clock() }) {
    return runTransaction(this.database, () => {
      const row = this.database
        .prepare(
          `SELECT reservation_id, request_id, user_id, provider_id,
                  reserved_tokens, created_at
           FROM model_budget_reservations
           WHERE reservation_id=? AND state='reserved'`,
        )
        .get(reservationId);
      if (!row) {
        throw new ModelBudgetStoreError("BUDGET_RESERVATION_NOT_ACTIVE");
      }
      const charged =
        chargeMode === "reserved" ? Number(row.reserved_tokens) : Number(totalTokens);
      if (!Number.isInteger(charged) || charged < 0) {
        throw new ModelBudgetStoreError("CHARGED_TOKENS_INVALID");
      }
      const settledAt = iso(epochMs);
      const result = this.database
        .prepare(
          `UPDATE model_budget_reservations
           SET state='settled', charged_tokens=?, input_tokens=?, output_tokens=?,
               usage_reported=?, charge_mode=?, reason_code=NULL, settled_at=?
           WHERE reservation_id=? AND state='reserved'`,
        )
        .run(
          charged,
          Number.isInteger(inputTokens) ? inputTokens : null,
          Number.isInteger(outputTokens) ? outputTokens : null,
          usageReported ? 1 : 0,
          chargeMode,
          settledAt,
          reservationId,
        );
      if (Number(result.changes) !== 1) {
        throw new ModelBudgetStoreError("BUDGET_RESERVATION_NOT_ACTIVE");
      }
      const { day, month } = utcKeys(Date.parse(row.created_at));
      this.#upsertUsage({
        userId: row.user_id,
        providerId: row.provider_id,
        day,
        inputTokens,
        outputTokens,
        totalTokens: charged,
        usageReported,
        epochMs,
      });
      return Object.freeze({
        requestId: row.request_id,
        userId: row.user_id,
        providerId: row.provider_id,
        day,
        month,
        inputTokens: Number.isInteger(inputTokens) ? inputTokens : null,
        outputTokens: Number.isInteger(outputTokens) ? outputTokens : null,
        totalTokens: charged,
        reservedTokens: Number(row.reserved_tokens),
        usageReported: Boolean(usageReported),
        chargeMode,
        occurredAt: epochMs,
      });
    });
  }

  release({ reservationId, reason = "not_charged", epochMs = this.clock() }) {
    const result = this.database
      .prepare(
        `UPDATE model_budget_reservations
         SET state='released', reason_code=?, settled_at=?
         WHERE reservation_id=? AND state='reserved'`,
      )
      .run(reason, iso(epochMs), reservationId);
    if (Number(result.changes) !== 1) {
      throw new ModelBudgetStoreError("BUDGET_RESERVATION_NOT_ACTIVE");
    }
    return Object.freeze({ reservationId, state: "released", reason });
  }

  // AC-048: aggregate only. No user dimension leaves this method.
  aggregateByProvider({ epochMs = this.clock() } = {}) {
    this.expireReservations({ epochMs });
    const { day } = utcKeys(epochMs);
    return this.database
      .prepare(
        `SELECT provider_id AS providerId, SUM(calls) AS calls,
                SUM(input_tokens) AS inputTokens, SUM(output_tokens) AS outputTokens,
                SUM(total_tokens) AS totalTokens,
                SUM(fallback_usage_records) AS fallbackCharges
         FROM model_token_usage_daily WHERE day=?
         GROUP BY provider_id ORDER BY provider_id`,
      )
      .all(day)
      .map((row) =>
        Object.freeze({
          providerId: row.providerId,
          calls: Number(row.calls || 0),
          inputTokens: Number(row.inputTokens || 0),
          outputTokens: Number(row.outputTokens || 0),
          totalTokens: Number(row.totalTokens || 0),
          fallbackCharges: Number(row.fallbackCharges || 0),
        }),
      );
  }
}

// Persisted circuit state over provider_circuits, so an open circuit survives a
// restart instead of releasing a stampede of retries.
class SqliteCircuitStore {
  constructor({ database, clock = () => Date.now() } = {}) {
    if (!database || typeof database.prepare !== "function") {
      throw new ModelBudgetStoreError("DATABASE_REQUIRED");
    }
    this.database = database;
    this.clock = clock;
  }

  get(key) {
    const row = this.database
      .prepare(
        `SELECT circuit_key, scope, user_id, provider_id, state,
                consecutive_failures, last_code, opened_at, retry_at,
                probe_in_flight
         FROM provider_circuits WHERE circuit_key=?`,
      )
      .get(key);
    if (!row) {
      return null;
    }
    return {
      key: row.circuit_key,
      scope: row.scope,
      userId: row.user_id,
      providerId: row.provider_id,
      state: row.state,
      consecutiveFailures: Number(row.consecutive_failures || 0),
      lastCode: row.last_code,
      openedAt: row.opened_at === null ? null : Number(row.opened_at),
      retryAt: row.retry_at === null ? null : Number(row.retry_at),
      probeInFlight: Boolean(row.probe_in_flight),
    };
  }

  set(key, value) {
    this.database
      .prepare(
        `INSERT INTO provider_circuits(
           circuit_key, scope, user_id, provider_id, state, consecutive_failures,
           last_code, opened_at, retry_at, probe_in_flight, updated_at
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(circuit_key) DO UPDATE SET
           scope=excluded.scope, user_id=excluded.user_id,
           provider_id=excluded.provider_id, state=excluded.state,
           consecutive_failures=excluded.consecutive_failures,
           last_code=excluded.last_code, opened_at=excluded.opened_at,
           retry_at=excluded.retry_at, probe_in_flight=excluded.probe_in_flight,
           updated_at=excluded.updated_at`,
      )
      .run(
        key,
        value.scope,
        value.userId || null,
        value.providerId,
        value.state,
        Number(value.consecutiveFailures || 0),
        value.lastCode || null,
        value.openedAt === undefined ? null : value.openedAt,
        value.retryAt === undefined ? null : value.retryAt,
        value.probeInFlight ? 1 : 0,
        iso(this.clock()),
      );
    return this.get(key);
  }

  delete(key) {
    this.database.prepare("DELETE FROM provider_circuits WHERE circuit_key=?").run(key);
  }

  values() {
    return this.database
      .prepare("SELECT circuit_key FROM provider_circuits ORDER BY circuit_key")
      .all()
      .map((row) => this.get(row.circuit_key));
  }
}

module.exports = {
  ModelBudgetStoreError,
  SqliteCircuitStore,
  SqliteModelBudgetLedger,
  runTransaction,
  utcKeys,
};
