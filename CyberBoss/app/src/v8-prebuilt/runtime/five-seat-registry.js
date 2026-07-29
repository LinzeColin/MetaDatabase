'use strict';

const SEAT_LIMIT = 5;

class FiveSeatRegistry {
  constructor({ db, clock = () => Date.now() } = {}) {
    if (!db || typeof db.prepare !== 'function') throw new TypeError('db is required');
    this.db = db;
    this.clock = clock;
    db.exec(`CREATE TABLE IF NOT EXISTS ordinary_user_seats(
      user_id TEXT PRIMARY KEY,
      seat_number INTEGER CHECK(seat_number BETWEEN 1 AND 5),
      state TEXT NOT NULL CHECK(state IN ('active','revoked')),
      claimed_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_ordinary_active_seat_number
      ON ordinary_user_seats(seat_number) WHERE state='active';`);
  }

  claim({ userId, role = 'user' }) {
    if (typeof userId !== 'string' || userId.length < 3) throw new TypeError('userId required');
    if (role === 'owner') return Object.freeze({ accepted: true, role: 'owner', seatNumber: null, ownerExempt: true });
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const existing = this.db.prepare('SELECT * FROM ordinary_user_seats WHERE user_id=?').get(userId);
      if (existing?.state === 'active') {
        this.db.exec('COMMIT');
        return Object.freeze({ accepted: true, role: 'user', seatNumber: Number(existing.seat_number), existing: true });
      }
      const used = new Set(this.db.prepare("SELECT seat_number FROM ordinary_user_seats WHERE state='active'").all().map((row) => Number(row.seat_number)));
      const seatNumber = [1, 2, 3, 4, 5].find((value) => !used.has(value));
      if (!seatNumber) {
        this.db.exec('COMMIT');
        return Object.freeze({ accepted: false, code: 'USER_CAPACITY_FULL', activeSeats: SEAT_LIMIT, seatLimit: SEAT_LIMIT, providerCalls: 0 });
      }
      const stamp = new Date(this.clock()).toISOString();
      this.db.prepare(`INSERT INTO ordinary_user_seats(user_id,seat_number,state,claimed_at,updated_at)
        VALUES(?,?,'active',?,?)
        ON CONFLICT(user_id) DO UPDATE SET seat_number=excluded.seat_number,state='active',updated_at=excluded.updated_at`)
        .run(userId, seatNumber, stamp, stamp);
      this.db.exec('COMMIT');
      return Object.freeze({ accepted: true, role: 'user', seatNumber, existing: false });
    } catch (error) {
      try { this.db.exec('ROLLBACK'); } catch {}
      throw error;
    }
  }

  revoke(userId) {
    return this.db.prepare("UPDATE ordinary_user_seats SET state='revoked',updated_at=? WHERE user_id=? AND state='active'")
      .run(new Date(this.clock()).toISOString(), userId).changes === 1;
  }

  snapshot() {
    const activeOrdinarySeats = Number(this.db.prepare("SELECT COUNT(*) AS count FROM ordinary_user_seats WHERE state='active'").get().count || 0);
    return Object.freeze({ activeOrdinarySeats, seatLimit: SEAT_LIMIT, remainingSeats: Math.max(0, SEAT_LIMIT - activeOrdinarySeats) });
  }
}

module.exports = { FiveSeatRegistry, SEAT_LIMIT };
