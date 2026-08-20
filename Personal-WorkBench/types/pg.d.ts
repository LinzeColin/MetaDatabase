declare module "pg" {
  export type QueryResultRow = Record<string, unknown>;
  export type FieldDef = { name: string };
  export type QueryResult<R extends QueryResultRow = QueryResultRow> = { rows: R[]; rowCount: number | null; fields: FieldDef[] };
  export interface PoolClient { query<R extends QueryResultRow = QueryResultRow>(text: string, values?: unknown[]): Promise<QueryResult<R>>; release(): void; }
  export class Pool { constructor(config?: Record<string, unknown>); query<R extends QueryResultRow = QueryResultRow>(text: string, values?: unknown[]): Promise<QueryResult<R>>; connect(): Promise<PoolClient>; end(): Promise<void>; }
  export const types: { setTypeParser(oid: number, parser: (value: string) => unknown): void };
}
