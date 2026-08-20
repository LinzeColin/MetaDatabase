import { Pool, type PoolClient, types as pgTypes } from "pg";

const INT8_OID = 20;
pgTypes.setTypeParser(INT8_OID, (value) => Number(value));

type Executor = Pool | PoolClient;
type BindValue = SqlBindValue;

type D1MetaShape = SqlResultMeta;

export function normalizeSqlBindValue(value: BindValue): unknown {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (value instanceof ArrayBuffer) return Buffer.from(value);
  if (ArrayBuffer.isView(value)) {
    return Buffer.from(value.buffer, value.byteOffset, value.byteLength);
  }
  return value;
}

export function placeholderSql(sql: string): string {
  let index = 0;
  let quote: "'" | '"' | null = null;
  let output = "";
  for (let cursor = 0; cursor < sql.length; cursor += 1) {
    const char = sql[cursor];
    if (quote) {
      output += char;
      if (char === quote) {
        if (sql[cursor + 1] === quote) {
          output += sql[cursor + 1];
          cursor += 1;
        } else {
          quote = null;
        }
      } else if (char === "\\" && quote === "'" && cursor + 1 < sql.length) {
        output += sql[cursor + 1];
        cursor += 1;
      }
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      output += char;
      continue;
    }
    if (char === "?") {
      index += 1;
      output += `$${index}`;
      continue;
    }
    output += char;
  }
  return output;
}

export function translateSql(input: string): string {
  let sql = input.trim();
  const insertOrIgnore = /^INSERT\s+OR\s+IGNORE\s+/i.test(sql);
  if (insertOrIgnore) sql = sql.replace(/^INSERT\s+OR\s+IGNORE\s+/i, "INSERT ");
  sql = placeholderSql(sql);
  if (insertOrIgnore && !/\bON\s+CONFLICT\b/i.test(sql)) {
    const returning = sql.match(/\s+RETURNING\s+[\s\S]+$/i);
    if (returning?.index !== undefined) {
      sql = `${sql.slice(0, returning.index)} ON CONFLICT DO NOTHING${sql.slice(returning.index)}`;
    } else {
      sql = `${sql} ON CONFLICT DO NOTHING`;
    }
  }
  return sql;
}

function meta(changes: number, rowsRead = 0): D1MetaShape {
  return {
    changed_db: changes > 0,
    changes,
    duration: 0,
    rows_read: rowsRead,
    rows_written: changes,
    size_after: 0,
  };
}

function isReadSql(sql: string): boolean {
  return /^\s*(?:SELECT|WITH\b[\s\S]*?\bSELECT|EXPLAIN|SHOW)\b/i.test(sql)
    || /\bRETURNING\b/i.test(sql);
}

export class PostgresPreparedStatement implements SqlPreparedStatement {
  readonly executor: Executor;
  readonly sql: string;
  readonly values: readonly unknown[];

  constructor(executor: Executor, sql: string, values: readonly unknown[] = []) {
    this.executor = executor;
    this.sql = sql;
    this.values = values;
  }

  bind(...values: BindValue[]): PostgresPreparedStatement {
    return new PostgresPreparedStatement(this.executor, this.sql, values.map(normalizeSqlBindValue));
  }

  withExecutor(executor: Executor): PostgresPreparedStatement {
    return new PostgresPreparedStatement(executor, this.sql, this.values);
  }

  private async query() {
    return this.executor.query(translateSql(this.sql), [...this.values]);
  }

  async first<T = Record<string, unknown>>(columnName?: string): Promise<T | null> {
    const result = await this.query();
    const row = result.rows[0] as Record<string, unknown> | undefined;
    if (!row) return null;
    if (columnName) return (row[columnName] ?? null) as T | null;
    return row as T;
  }

  async all<T = Record<string, unknown>>(): Promise<SqlResult<T>> {
    const result = await this.query();
    return {
      success: true,
      results: result.rows as T[],
      meta: meta(0, result.rowCount ?? result.rows.length),
    };
  }

  async raw<T = unknown[]>(options?: { columnNames?: boolean }): Promise<T[]> {
    const result = await this.query();
    const rows = result.rows.map((row) => result.fields.map((field) => row[field.name]));
    if (options?.columnNames) rows.unshift(result.fields.map((field) => field.name));
    return rows as T[];
  }

  async run<T = Record<string, unknown>>(): Promise<SqlResult<T>> {
    const started = performance.now();
    const result = await this.query();
    const rows = isReadSql(this.sql) ? (result.rows as T[]) : [];
    const changes = result.rowCount ?? 0;
    return {
      success: true,
      results: rows,
      meta: { ...meta(changes, rows.length), duration: performance.now() - started },
    };
  }
}

export class PostgresSqlDatabase implements SqlDatabase {
  readonly pool: Pool;

  constructor(pool: Pool) {
    this.pool = pool;
  }

  prepare(sql: string): PostgresPreparedStatement {
    return new PostgresPreparedStatement(this.pool, sql);
  }

  async batch<T = Record<string, unknown>>(statements: SqlPreparedStatement[]): Promise<SqlResult<T>[]> {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const results: SqlResult<T>[] = [];
      for (const statement of statements) {
        if (!(statement instanceof PostgresPreparedStatement)) {
          throw new TypeError("The batch contains a statement from another database adapter.");
        }
        results.push(await statement.withExecutor(client).run<T>());
      }
      await client.query("COMMIT");
      return results;
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
  }

  async exec(sql: string): Promise<{ count: number; duration: number }> {
    const started = performance.now();
    await this.pool.query(sql);
    const count = sql.split(";").filter((statement) => statement.trim()).length;
    return { count, duration: performance.now() - started };
  }
}

let runtimePool: Pool | null = null;
let runtimeDatabase: PostgresSqlDatabase | null = null;

export function getPostgresPool(): Pool {
  if (!runtimePool) {
    const connectionString = process.env.DATABASE_URL?.trim();
    if (!connectionString) throw new Error("DATABASE_URL is required for Personal Workbench.");
    runtimePool = new Pool({
      connectionString,
      max: Number(process.env.DATABASE_POOL_MAX || 10),
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 10_000,
      application_name: "personal-workbench",
    });
  }
  return runtimePool;
}

export function getVps3Database(): SqlDatabase {
  if (!runtimeDatabase) runtimeDatabase = new PostgresSqlDatabase(getPostgresPool());
  return runtimeDatabase;
}
