// EEI cloud user-state routes (S10PBT01). 云端即真相: state written here
// is authoritative for the cloud product; nothing syncs back to the local
// factory. Contracts mirror the local FastAPI saved-view/watchlist shapes
// the web client already speaks (apps/web/src/app/saved-view-client.ts).

function nowIso() {
  return new Date().toISOString();
}

function parseJson(text, fallback) {
  if (!text) return fallback;
  try {
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

async function savedViewRecord(env, id) {
  const row = await env.EEI_PUB.prepare(
    "SELECT id, name, description, workspace_key, state_json, schema_version," +
      " current_version, metadata_json, updated_at," +
      " (SELECT COUNT(*) FROM saved_view_versions v WHERE v.view_id = saved_views.id)" +
      " AS version_count" +
      " FROM saved_views WHERE id = ?"
  )
    .bind(id)
    .first();
  if (!row) return null;
  return {
    id: row.id,
    name: row.name,
    description: row.description,
    workspace_key: row.workspace_key,
    state: parseJson(row.state_json, {}),
    schema_version: row.schema_version,
    current_version: row.current_version,
    version_count: row.version_count,
    updated_at: row.updated_at,
    metadata: parseJson(row.metadata_json, {})
  };
}

export async function createSavedView(env, body, json, badRequest) {
  if (!body?.name || typeof body.state !== "object" || body.state === null) {
    return badRequest("name and state are required");
  }
  const id = crypto.randomUUID();
  const timestamp = nowIso();
  await env.EEI_PUB.batch([
    env.EEI_PUB.prepare(
      "INSERT INTO saved_views(id, name, description, workspace_key, state_json," +
        " schema_version, current_version, metadata_json, created_at, updated_at)" +
        " VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)"
    ).bind(
      id,
      body.name,
      body.description ?? null,
      body.workspace_key ?? "mvp",
      JSON.stringify(body.state),
      body.schema_version ?? "saved-view-v1",
      JSON.stringify(body.metadata ?? {}),
      timestamp,
      timestamp
    ),
    env.EEI_PUB.prepare(
      "INSERT INTO saved_view_versions(view_id, version_no, state_json, change_note, created_at)" +
        " VALUES (?, 1, ?, ?, ?)"
    ).bind(id, JSON.stringify(body.state), body.change_note ?? null, timestamp)
  ]);
  return json(await savedViewRecord(env, id), 201);
}

export async function updateSavedView(env, id, body, json, badRequest, notFound) {
  if (typeof body?.state !== "object" || body.state === null) {
    return badRequest("state is required");
  }
  const existing = await env.EEI_PUB.prepare(
    "SELECT id, current_version FROM saved_views WHERE id = ?"
  )
    .bind(id)
    .first();
  if (!existing) {
    return notFound(`Saved view not found: ${id}`);
  }
  const expected = Number.parseInt(body.expected_version, 10);
  if (!Number.isFinite(expected) || expected !== existing.current_version) {
    return json(
      {
        detail: {
          reason: "saved_view_version_conflict",
          current_version: existing.current_version,
          expected_version: body.expected_version ?? null
        }
      },
      409
    );
  }
  const nextVersion = existing.current_version + 1;
  const timestamp = nowIso();
  await env.EEI_PUB.batch([
    env.EEI_PUB.prepare(
      "UPDATE saved_views SET state_json = ?, description = COALESCE(?, description)," +
        " metadata_json = ?, current_version = ?, updated_at = ? WHERE id = ?"
    ).bind(
      JSON.stringify(body.state),
      body.description ?? null,
      JSON.stringify(body.metadata ?? {}),
      nextVersion,
      timestamp,
      id
    ),
    env.EEI_PUB.prepare(
      "INSERT INTO saved_view_versions(view_id, version_no, state_json, change_note, created_at)" +
        " VALUES (?, ?, ?, ?, ?)"
    ).bind(id, nextVersion, JSON.stringify(body.state), body.change_note ?? null, timestamp)
  ]);
  return json(await savedViewRecord(env, id));
}

export async function getSavedView(env, id, json, notFound) {
  const record = await savedViewRecord(env, id);
  if (!record) {
    return notFound(`Saved view not found: ${id}`);
  }
  return json(record);
}

// List all saved views (newest first). The web drawer's saved-views tab calls
// GET /v1/saved-views (P2-9); the Worker previously only had create/get/update.
export async function listSavedViews(env, json) {
  const { results } = await env.EEI_PUB.prepare(
    "SELECT id FROM saved_views ORDER BY updated_at DESC"
  ).all();
  const records = [];
  for (const row of results ?? []) {
    const record = await savedViewRecord(env, row.id);
    if (record) records.push(record);
  }
  return json(records);
}

export async function listWatchlists(env, json) {
  const { results: lists } = await env.EEI_PUB.prepare(
    "SELECT id, name, created_at FROM watchlists ORDER BY created_at"
  ).all();
  const { results: items } = await env.EEI_PUB.prepare(
    "SELECT watchlist_id, entity_id, added_at FROM watchlist_items ORDER BY added_at"
  ).all();
  const byList = new Map();
  for (const item of items ?? []) {
    const bucket = byList.get(item.watchlist_id) ?? [];
    bucket.push({ entity_id: item.entity_id, added_at: item.added_at });
    byList.set(item.watchlist_id, bucket);
  }
  return json(
    (lists ?? []).map((list) => ({
      id: list.id,
      name: list.name,
      created_at: list.created_at,
      items: byList.get(list.id) ?? []
    }))
  );
}

export async function createWatchlist(env, body, json, badRequest) {
  if (!body?.name) {
    return badRequest("name is required");
  }
  const id = crypto.randomUUID();
  await env.EEI_PUB.prepare(
    "INSERT INTO watchlists(id, name, created_at) VALUES (?, ?, ?)"
  )
    .bind(id, body.name, nowIso())
    .run();
  return json({ id, name: body.name, items: [] }, 201);
}

export async function addWatchlistItem(env, watchlistId, body, json, badRequest, notFound) {
  if (!body?.entity_id) {
    return badRequest("entity_id is required");
  }
  const list = await env.EEI_PUB.prepare("SELECT id FROM watchlists WHERE id = ?")
    .bind(watchlistId)
    .first();
  if (!list) {
    return notFound(`Watchlist not found: ${watchlistId}`);
  }
  await env.EEI_PUB.prepare(
    "INSERT OR REPLACE INTO watchlist_items(watchlist_id, entity_id, added_at)" +
      " VALUES (?, ?, ?)"
  )
    .bind(watchlistId, body.entity_id, nowIso())
    .run();
  return json({ watchlist_id: watchlistId, entity_id: body.entity_id }, 201);
}

// Unfollow: remove one entity from a watchlist. The web drawer's optimistic
// unfollow calls DELETE /v1/watchlists/:id/items?entity_id=... (P2-9). Idempotent.
export async function removeWatchlistItem(env, watchlistId, entityId, json, badRequest, notFound) {
  if (!entityId) {
    return badRequest("entity_id is required");
  }
  const list = await env.EEI_PUB.prepare("SELECT id FROM watchlists WHERE id = ?")
    .bind(watchlistId)
    .first();
  if (!list) {
    return notFound(`Watchlist not found: ${watchlistId}`);
  }
  await env.EEI_PUB.prepare(
    "DELETE FROM watchlist_items WHERE watchlist_id = ? AND entity_id = ?"
  )
    .bind(watchlistId, entityId)
    .run();
  return json({ watchlist_id: watchlistId, entity_id: entityId, removed: true });
}

export async function appendExplorationLog(env, body, json, badRequest) {
  if (!body?.action) {
    return badRequest("action is required");
  }
  const id = crypto.randomUUID();
  await env.EEI_PUB.prepare(
    "INSERT INTO exploration_log(id, session_id, action, focus_entity_id, payload_json, created_at)" +
      " VALUES (?, ?, ?, ?, ?, ?)"
  )
    .bind(
      id,
      body.session_id ?? null,
      body.action,
      body.focus_entity_id ?? null,
      JSON.stringify(body.payload ?? {}),
      nowIso()
    )
    .run();
  return json({ id, action: body.action }, 201);
}

export async function listExplorationLog(env, limit, json) {
  const bounded = Math.max(1, Math.min(Number.parseInt(limit ?? "20", 10) || 20, 100));
  const { results } = await env.EEI_PUB.prepare(
    "SELECT id, session_id, action, focus_entity_id, payload_json, created_at" +
      " FROM exploration_log ORDER BY created_at DESC LIMIT ?"
  )
    .bind(bounded)
    .all();
  return json(
    (results ?? []).map((row) => ({
      id: row.id,
      session_id: row.session_id,
      action: row.action,
      focus_entity_id: row.focus_entity_id,
      payload: parseJson(row.payload_json, {}),
      created_at: row.created_at
    }))
  );
}
