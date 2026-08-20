type SqlBindValue = string | number | bigint | boolean | Date | null | ArrayBuffer | ArrayBufferView;

type SqlResultMeta = {
  changed_db: boolean;
  changes: number;
  duration: number;
  last_row_id?: number | bigint;
  rows_read: number;
  rows_written: number;
  size_after: number;
};

type SqlResult<T = Record<string, unknown>> = {
  success: true;
  results: T[];
  meta: SqlResultMeta;
};

interface SqlPreparedStatement {
  readonly sql: string;
  readonly values: readonly unknown[];
  bind(...values: SqlBindValue[]): SqlPreparedStatement;
  first<T = Record<string, unknown>>(columnName?: string): Promise<T | null>;
  all<T = Record<string, unknown>>(): Promise<SqlResult<T>>;
  raw<T = unknown[]>(options?: { columnNames?: boolean }): Promise<T[]>;
  run<T = Record<string, unknown>>(): Promise<SqlResult<T>>;
}

interface SqlDatabase {
  prepare(sql: string): SqlPreparedStatement;
  batch<T = Record<string, unknown>>(statements: SqlPreparedStatement[]): Promise<SqlResult<T>[]>;
  exec(sql: string): Promise<{ count: number; duration: number }>;
}

type StoredObject = {
  key: string;
  size: number;
  etag: string;
  httpEtag: string;
  uploaded: Date;
  httpMetadata?: { contentType?: string };
  customMetadata?: Record<string, string>;
  writeHttpMetadata?(headers: Headers): void;
};

type ObjectBody = StoredObject & {
  body: ReadableStream<Uint8Array>;
  bodyUsed: boolean;
};

interface ObjectBucket {
  put(
    key: string,
    body: ArrayBuffer | ArrayBufferView | Blob | string,
    options?: {
      httpMetadata?: { contentType?: string };
      customMetadata?: Record<string, string>;
    },
  ): Promise<StoredObject>;
  get(key: string): Promise<ObjectBody | null>;
  head(key: string): Promise<StoredObject | null>;
  delete(key: string | string[]): Promise<void>;
}

/*
 * Drizzle's D1 driver is retained only as an internal query-shape adapter.
 * These aliases are implemented by the PostgreSQL runtime below; no
 * Cloudflare Worker, D1 database or R2 bucket is used in production.
 */
type D1Database = SqlDatabase;
type D1PreparedStatement = SqlPreparedStatement;
type D1Result<T = Record<string, unknown>> = SqlResult<T>;
type R2Bucket = ObjectBucket;
type R2Object = StoredObject;
type R2ObjectBody = ObjectBody;
