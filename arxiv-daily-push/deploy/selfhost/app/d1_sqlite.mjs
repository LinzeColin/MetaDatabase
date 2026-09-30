// D1 兼容层：让 deploy/cloudflare/worker_cloud.js 里所有 env.DB.prepare(...).bind(...).first()/all()/run() 和
// env.DB.batch([...]) 原样跑在服务器本地的 SQLite 文件上（Node 内置 node:sqlite，零第三方依赖）。
//
// 只实现 worker 真正用到的那一小块 D1 API，行为对齐 Cloudflare D1：
//   · bind 之前不执行；first() 无行返回 null；all() 返回 { results, success, meta }；
//   · run() 的 meta 带 changes / last_row_id（gradeRecall 要读 ins.meta.last_row_id）；
//   · batch() 是一个事务：任何一条失败整批回滚（D1 的 batch 也是原子的）。
// 不碰任何网络、不依赖 Cloudflare。
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

// node:sqlite 把 JS number 一律按 REAL 绑定（LIMIT ? / 主键比较会出问题）；D1 对整数按 INTEGER 绑定。
// 这里对齐 D1：整数值 → BigInt（INTEGER），其余 number → REAL；undefined/NaN 与 D1 一样是错误，不静默成 NULL。
function toSqlValue(v, idx) {
  if (v === null) return null;
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) throw new Error(`D1_TYPE_ERROR: non-finite number at bind index ${idx}`);
    return Number.isInteger(v) && Math.abs(v) <= Number.MAX_SAFE_INTEGER ? BigInt(v) : v;
  }
  if (typeof v === 'boolean') return v ? 1n : 0n;
  if (typeof v === 'string' || typeof v === 'bigint') return v;
  if (v instanceof ArrayBuffer) return new Uint8Array(v);
  if (ArrayBuffer.isView(v)) return new Uint8Array(v.buffer, v.byteOffset, v.byteLength);
  throw new Error(`D1_TYPE_ERROR: type '${v === undefined ? 'undefined' : typeof v}' not supported at bind index ${idx}`);
}
const plainRow = (r) => ({ ...r });

export class D1Statement {
  constructor(db, sql, params = []) { this._db = db; this._sql = sql; this._params = params; }
  bind(...params) { return new D1Statement(this._db, this._sql, params.map((p, i) => toSqlValue(p, i))); }
  _exec(mode) {
    const st = this._db._h.prepare(this._sql);
    const t0 = performance.now();
    if (mode === 'run') {
      const r = st.run(...this._params);
      return { results: [], success: true, meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid), duration: performance.now() - t0 } };
    }
    const rows = st.all(...this._params).map(plainRow);
    return { results: rows, success: true, meta: { changes: 0, rows_read: rows.length, duration: performance.now() - t0 } };
  }
  async first(col) {
    const r = this._exec('all').results[0];
    if (r === undefined) return null;
    return col ? r[col] : r;
  }
  async all() { return this._exec('all'); }
  async run() { return this._exec('run'); }
  async raw() { return this._exec('all').results.map((r) => Object.values(r)); }
}

export class D1Database {
  constructor(handle) { this._h = handle; }
  prepare(sql) { return new D1Statement(this, sql); }
  async batch(stmts) {
    const out = [];
    this._h.exec('BEGIN IMMEDIATE');
    try {
      for (const s of stmts) out.push(s._exec(/^\s*(select|with|pragma)\b/i.test(s._sql) ? 'all' : 'run'));
      this._h.exec('COMMIT');
    } catch (e) {
      try { this._h.exec('ROLLBACK'); } catch (_) { /* 事务已被 SQLite 自己回滚 */ }
      throw e;
    }
    return out;
  }
  async exec(sql) { this._h.exec(sql); return { count: 1, duration: 0 }; }
  close() { this._h.close(); }
}

// 打开（必要时新建）本地库：WAL + busy_timeout（网页容器与每日任务容器是两个进程，同写一个文件），
// 并把 schema_cloud.sql 幂等应用一遍（全部 IF NOT EXISTS，已有数据不动）。
export function openDatabase(dbPath, schemaPath) {
  if (dbPath !== ':memory:') mkdirSync(dirname(dbPath), { recursive: true });
  const h = new DatabaseSync(dbPath);
  h.exec('PRAGMA journal_mode=WAL');
  h.exec('PRAGMA busy_timeout=15000');
  h.exec('PRAGMA synchronous=NORMAL');
  h.exec('PRAGMA foreign_keys=OFF');   // D1 默认也不强制外键；schema 里本就没有外键
  if (schemaPath) h.exec(readFileSync(schemaPath, 'utf8'));
  return new D1Database(h);
}
