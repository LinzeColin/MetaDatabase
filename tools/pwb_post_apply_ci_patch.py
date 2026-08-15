#!/usr/bin/env python3
from pathlib import Path

root = Path("Personal-WorkBench/server/runtime/vps3")

sqlite = root / "sqlite-d1.ts"
text = sqlite.read_text(encoding="utf-8")
text = text.replace(
'''export class SqliteD1PreparedStatement {
  constructor(
    private readonly database: Database.Database,
    readonly sql: string,
    readonly values: Array<string | number | bigint | null | Buffer> = [],
  ) {}
''',
'''export class SqliteD1PreparedStatement {
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
''')
text = text.replace(
'''export class SqliteD1Database {
  constructor(readonly sqlite: Database.Database) {}
''',
'''export class SqliteD1Database {
  readonly sqlite: Database.Database;

  constructor(sqlite: Database.Database) {
    this.sqlite = sqlite;
  }
''')
sqlite.write_text(text, encoding="utf-8")

r2 = root / "r2-s3.ts"
text = r2.read_text(encoding="utf-8")
text = text.replace(
'''export class R2S3Bucket {
  private client: S3Client | null = null;

  constructor(private readonly config: ObjectStoreConfig) {}
''',
'''export class R2S3Bucket {
  private client: S3Client | null = null;
  private readonly config: ObjectStoreConfig;

  constructor(config: ObjectStoreConfig) {
    this.config = config;
  }
''')
r2.write_text(text, encoding="utf-8")
