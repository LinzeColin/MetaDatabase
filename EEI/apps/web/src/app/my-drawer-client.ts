"use client";

// P2-9 「我的」抽屉数据层（UX_SPEC_EEI v1.0 §A.2 顶栏 / §G-P2-9）。
// 关注（watchlist）+ 保存视图（saved views）+ 探索记录（exploration log）三合一，
// 外加铃铛未读角标（/v1/changes）。请求形状对齐线上云 Worker
// （apps/cloudflare-public/src/user_state.mjs）：watchlist item 以 entity_id 为键，
// 列表接口返回裸数组。未配置 API base（本地样例态 / 未登录）时一律返回诚实空态，
// 绝不造数据。关注/取消关注走乐观更新，失败回滚由调用方（my-drawer.tsx）承担。

import { readProductionDataApiBaseUrl } from "./production-data-client";

export type WatchlistItemRecord = {
  entity_id: string;
  added_at?: string | null;
  label?: string | null;
};

export type WatchlistRecord = {
  id: string;
  name: string;
  created_at?: string | null;
  items: WatchlistItemRecord[];
};

export type SavedViewSummary = {
  id: string;
  name: string;
  updated_at?: string | null;
  workspace_key?: string | null;
};

export type ExplorationLogEntry = {
  id: string;
  action: string;
  focus_entity_id?: string | null;
  created_at?: string | null;
  label?: string | null;
};

export type DrawerFetch<T> =
  | { status: "ok"; data: T }
  | { status: "empty"; reason: "api_base_missing" }
  | { status: "error"; reason: string };

function apiBase(): string {
  // 抽屉在 SSR/静态导出预渲染期不触网；仅浏览器侧读取 base。
  if (typeof window === "undefined") {
    return "";
  }
  return readProductionDataApiBaseUrl();
}

async function getJson(path: string): Promise<{ ok: boolean; status: number; body: unknown }> {
  const base = apiBase();
  const response = await window.fetch(`${base}${path}`);
  const body = (await response.json().catch(() => null)) as unknown;
  return { ok: response.ok, status: response.status, body };
}

// —— 关注列表 ————————————————————————————————————————————————
export async function loadWatchlists(): Promise<DrawerFetch<WatchlistRecord[]>> {
  if (!apiBase()) {
    return { status: "empty", reason: "api_base_missing" };
  }
  try {
    const { ok, status, body } = await getJson("/v1/watchlists");
    if (!ok || !Array.isArray(body)) {
      return { status: "error", reason: `http_${status}` };
    }
    return { status: "ok", data: body.map(normalizeWatchlist) };
  } catch (error) {
    return { status: "error", reason: errorName(error) };
  }
}

/** 无任何关注列表时按需创建默认「我的关注」，返回其 id（乐观关注的落点）。 */
export async function ensureDefaultWatchlist(
  existing: WatchlistRecord[]
): Promise<{ status: "ok"; id: string } | { status: "error"; reason: string }> {
  if (existing.length > 0) {
    return { status: "ok", id: existing[0].id };
  }
  const base = apiBase();
  if (!base) {
    return { status: "error", reason: "api_base_missing" };
  }
  try {
    const response = await window.fetch(`${base}/v1/watchlists`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: "我的关注" })
    });
    const body = (await response.json().catch(() => null)) as { id?: unknown } | null;
    if (!response.ok || typeof body?.id !== "string") {
      return { status: "error", reason: `http_${response.status}` };
    }
    return { status: "ok", id: body.id };
  } catch (error) {
    return { status: "error", reason: errorName(error) };
  }
}

export async function followEntity(
  watchlistId: string,
  entityId: string
): Promise<{ status: "ok" } | { status: "error"; reason: string }> {
  const base = apiBase();
  if (!base) {
    return { status: "error", reason: "api_base_missing" };
  }
  try {
    const response = await window.fetch(
      `${base}/v1/watchlists/${encodeURIComponent(watchlistId)}/items`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ entity_id: entityId })
      }
    );
    if (!response.ok) {
      return { status: "error", reason: `http_${response.status}` };
    }
    return { status: "ok" };
  } catch (error) {
    return { status: "error", reason: errorName(error) };
  }
}

export async function unfollowEntity(
  watchlistId: string,
  entityId: string
): Promise<{ status: "ok" } | { status: "error"; reason: string }> {
  const base = apiBase();
  if (!base) {
    return { status: "error", reason: "api_base_missing" };
  }
  try {
    const response = await window.fetch(
      `${base}/v1/watchlists/${encodeURIComponent(watchlistId)}/items?entity_id=${encodeURIComponent(
        entityId
      )}`,
      { method: "DELETE" }
    );
    // 204 No Content 也算成功；部分后端返回 200。
    if (!response.ok) {
      return { status: "error", reason: `http_${response.status}` };
    }
    return { status: "ok" };
  } catch (error) {
    return { status: "error", reason: errorName(error) };
  }
}

// —— 保存视图 ————————————————————————————————————————————————
export async function loadSavedViews(): Promise<DrawerFetch<SavedViewSummary[]>> {
  if (!apiBase()) {
    return { status: "empty", reason: "api_base_missing" };
  }
  try {
    const { ok, status, body } = await getJson("/v1/saved-views");
    if (!ok || !Array.isArray(body)) {
      return { status: "error", reason: `http_${status}` };
    }
    return { status: "ok", data: body.map(normalizeSavedView) };
  } catch (error) {
    return { status: "error", reason: errorName(error) };
  }
}

// —— 探索记录 ————————————————————————————————————————————————
export async function loadExplorationLog(
  limit = 20
): Promise<DrawerFetch<ExplorationLogEntry[]>> {
  if (!apiBase()) {
    return { status: "empty", reason: "api_base_missing" };
  }
  try {
    const { ok, status, body } = await getJson(
      `/v1/exploration-log?limit=${encodeURIComponent(String(limit))}`
    );
    if (!ok || !Array.isArray(body)) {
      return { status: "error", reason: `http_${status}` };
    }
    return { status: "ok", data: body.map(normalizeLogEntry) };
  } catch (error) {
    return { status: "error", reason: errorName(error) };
  }
}

// —— 未读变化角标 —————————————————————————————————————————————
export async function loadUnreadCount(since?: string): Promise<number | null> {
  if (!apiBase()) {
    return null;
  }
  try {
    const query = since ? `?since=${encodeURIComponent(since)}` : "";
    const { ok, body } = await getJson(`/v1/changes${query}`);
    if (!ok || !Array.isArray(body)) {
      return null;
    }
    return body.length;
  } catch {
    return null;
  }
}

function normalizeWatchlist(value: unknown): WatchlistRecord {
  const record = (value ?? {}) as Record<string, unknown>;
  const rawItems = Array.isArray(record.items) ? record.items : [];
  return {
    id: typeof record.id === "string" ? record.id : "",
    name: typeof record.name === "string" ? record.name : "关注",
    created_at: typeof record.created_at === "string" ? record.created_at : null,
    items: rawItems.map(normalizeWatchlistItem).filter((item) => item.entity_id)
  };
}

function normalizeWatchlistItem(value: unknown): WatchlistItemRecord {
  const record = (value ?? {}) as Record<string, unknown>;
  // 云 Worker 用 entity_id；FastAPI 用 object_id——两者都收。
  const entityId =
    typeof record.entity_id === "string"
      ? record.entity_id
      : typeof record.object_id === "string"
        ? record.object_id
        : "";
  return {
    entity_id: entityId,
    added_at: typeof record.added_at === "string" ? record.added_at : null,
    label: typeof record.label === "string" ? record.label : null
  };
}

function normalizeSavedView(value: unknown): SavedViewSummary {
  const record = (value ?? {}) as Record<string, unknown>;
  return {
    id: typeof record.id === "string" ? record.id : "",
    name: typeof record.name === "string" ? record.name : "未命名视图",
    updated_at: typeof record.updated_at === "string" ? record.updated_at : null,
    workspace_key: typeof record.workspace_key === "string" ? record.workspace_key : null
  };
}

function normalizeLogEntry(value: unknown): ExplorationLogEntry {
  const record = (value ?? {}) as Record<string, unknown>;
  const payload = (record.payload ?? {}) as Record<string, unknown>;
  return {
    id: typeof record.id === "string" ? record.id : `${Math.random()}`,
    action: typeof record.action === "string" ? record.action : "explore",
    focus_entity_id:
      typeof record.focus_entity_id === "string" ? record.focus_entity_id : null,
    created_at: typeof record.created_at === "string" ? record.created_at : null,
    label: typeof payload.label === "string" ? payload.label : null
  };
}

function errorName(error: unknown): string {
  return error instanceof Error ? error.name : "fetch_failed";
}
