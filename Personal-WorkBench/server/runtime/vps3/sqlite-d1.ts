import Database from "better-sqlite3";

type BindValue = string | number | bigint | boolean | null | ArrayBuffer | ArrayBufferView;

type D1MetaShape = {
  changed_db: boolean;
  changes: number;
  duration: number;
  last_row_id?: number | bigint;
  rows_read: number;
  rows_written: number;
  size_after: number;
};

function normalizeValue(value: BindValue): string | number | bigint | null | Buffer {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (value instanceof ArrayBuffer) return Buffer.from(value);
  if (ArrayBuffer.isView(value)) {
    return Buffer.from(value.buffer, value.byteOffset, value.byteLength);
  }
  return value;
}

function isRowStatement(sql: string): boolean {
  return /^\s*(?:SELECT|PRAGMA|WITH\b[\s\S]*?\bSELECT|EXPLAIN)/i.test(sql)
    || /\bRETURNING\b/i.test(sql);
}

function meta(changes: number, rowsRead = 0, lastRowId?: number | bigint): D1MetaShape {
  return {
    changed_db: changes > 0,
    changes,
    duration: 0,
    ...(lastRowId === undefined ? {} : { last_row_id: lastRowId }),
    rows_read: rowsRead,
    rows_written: changes,
    size_after: 0,
  };
}

export class SqliteD1PreparedStatement {
  private readonly database: Database.Database;
  readonly sql: string;
  readonly values: Array<string | number | bigint | null | Buffer>;

  constructor(
    database: Database.Database,
    sql: string,
    values: Array<string | number | bigint | null | Buffer> = [],
  ) {
    this.database = database;
    this.sql = sql;
    this.values = values;
  }

  bind(...values: BindValue[]): SqliteD1PreparedStatement {
    return new SqliteD1PreparedStatement(this.database, this.sql, values.map(normalizeValue));
  }

  async first<T = Record<string, unknown>>(columnName?: string): Promise<T | null> {
    const row = this.database.prepare(this.sql).get(...this.values) as Record<string, unknown> | undefined;
    if (!row) return null;
    if (columnName) return (row[columnName] ?? null) as T | null;
    return row as T;
  }

  async all<T = Record<string, unknown>>() {
    const results = this.database.prepare(this.sql).all(...this.values) as T[];
    return { success: true, results, meta: meta(0, results.length) };
  }

  async raw<T = unknown[]>(options?: { columnNames?: boolean }): Promise<T[]> {
    const statement = this.database.prepare(this.sql).raw(true);
    const rows = statement.all(...this.values) as unknown[][];
    if (options?.columnNames) {
      rows.unshift(statement.columns().map((column) => column.name));
    }
    return rows as T[];
  }

  executeSync<T = Record<string, unknown>>() {
    if (isRowStatement(this.sql)) {
      const results = this.database.prepare(this.sql).all(...this.values) as T[];
      return { success: true, results, meta: meta(0, results.length) };
    }
    const result = this.database.prepare(this.sql).run(...this.values);
    return {
      success: true,
      results: [] as T[],
      meta: meta(result.changes, 0, result.lastInsertRowid),
    };
  }

  async run<T = Record<string, unknown>>() {
    return this.executeSync<T>();
  }
}

export class SqliteD1Database {
  readonly sqlite: Database.Database;

  constructor(sqlite: Database.Database) {
    this.sqlite = sqlite;
  }

  prepare(sql: string): SqliteD1PreparedStatement {
    return new SqliteD1PreparedStatement(this.sqlite, sql);
  }

  async batch<T = Record<string, unknown>>(statements: SqliteD1PreparedStatement[]) {
    const execute = this.sqlite.transaction((items: SqliteD1PreparedStatement[]) =>
      items.map((statement) => {
        if (!(statement instanceof SqliteD1PreparedStatement)) {
          throw new TypeError("The batch contains a statement from another database adapter.");
        }
        return statement.executeSync<T>();
      }),
    );
    return execute(statements);
  }

  async exec(sql: string) {
    const started = performance.now();
    this.sqlite.exec(sql);
    const count = sql.split(";").filter((statement) => statement.trim()).length;
    return { count, duration: performance.now() - started };
  }
}

export function configureSqlite(database: Database.Database): void {
  database.pragma("foreign_keys = ON");
  database.pragma("journal_mode = WAL");
  database.pragma("synchronous = NORMAL");
  database.pragma("busy_timeout = 5000");
}

let runtimeDatabase: SqliteD1Database | null = null;

export function getVps3Database(): D1Database {
  if (!runtimeDatabase) {
    const databasePath = process.env.RUNTIME_DB_PATH?.trim() || "./.runtime/personal-workbench.sqlite3";
    const sqlite = new Database(databasePath);
    configureSqlite(sqlite);
    runtimeDatabase = new SqliteD1Database(sqlite);
  }
  return runtimeDatabase as unknown as D1Database;
}
