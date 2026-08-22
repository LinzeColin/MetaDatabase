export const DEFAULT_STATE = Object.freeze({
  version: 1,
  mode: "gallery",
  selected: null,
  intervalMs: 4 * 60 * 60 * 1000,
  hidden: [],
  cycle: [],
  cursor: 0,
  lastRotate: 0,
  updated: 0,
  catalogGenerated: "",
});

export const WRITABLE_STATE_FIELDS = Object.freeze([
  "mode", "selected", "intervalMs", "hidden", "cycle", "cursor", "lastRotate",
]);

export function normalizeState(raw = {}, catalog = { entries: [] }) {
  const ids = new Set((catalog.entries || []).map((entry) => entry.id));
  const state = { ...DEFAULT_STATE, ...raw };
  state.catalogGenerated = typeof state.catalogGenerated === "string" ? state.catalogGenerated : "";
  state.mode = state.mode === "rotate" ? "rotate" : "gallery";
  state.intervalMs = Number.isFinite(Number(state.intervalMs)) && Number(state.intervalMs) >= 60000
    ? Number(state.intervalMs) : DEFAULT_STATE.intervalMs;
  state.hidden = [...new Set(Array.isArray(state.hidden) ? state.hidden.filter((id) => ids.has(id)) : [])];
  state.cycle = Array.isArray(state.cycle) ? state.cycle.filter((id) => ids.has(id) && !state.hidden.includes(id)) : [];
  state.cursor = Math.max(0, Math.min(Number(state.cursor) || 0, state.cycle.length));
  if (!ids.has(state.selected) || state.hidden.includes(state.selected)) state.selected = null;
  return state;
}

export function patchState(current, patch, catalog, now = Date.now()) {
  const next = { ...current };
  for (const field of WRITABLE_STATE_FIELDS) {
    if (Object.hasOwn(patch || {}, field)) next[field] = patch[field];
  }
  next.updated = now;
  return normalizeState(next, catalog);
}

export function shuffledCycle(catalog, hidden = [], random = Math.random) {
  const blocked = new Set(hidden);
  const ids = (catalog.entries || []).map((entry) => entry.id).filter((id) => !blocked.has(id));
  for (let index = ids.length - 1; index > 0; index -= 1) {
    const other = Math.floor(random() * (index + 1));
    [ids[index], ids[other]] = [ids[other], ids[index]];
  }
  return ids;
}

function advanceState(raw, catalog, now, random) {
  const state = normalizeState(raw, catalog);
  const visibleCount = (catalog.entries || []).filter((entry) => !state.hidden.includes(entry.id)).length;
  if (!visibleCount) return state;

  for (let pass = 0; pass < 2; pass += 1) {
    if (!state.cycle.length || state.cursor >= state.cycle.length) {
      state.cycle = shuffledCycle(catalog, state.hidden, random);
      state.cursor = 0;
      if (visibleCount > 1 && state.cycle[0] === state.selected) {
        state.cycle.push(state.cycle.shift());
      }
    }
    while (state.cursor < state.cycle.length) {
      const selected = state.cycle[state.cursor];
      state.cursor += 1;
      if (visibleCount > 1 && selected === state.selected) continue;
      state.selected = selected;
      state.lastRotate = now;
      state.updated = now;
      return state;
    }
  }
  return state;
}

export function nextState(raw, catalog, now = Date.now(), random = Math.random) {
  return advanceState(raw, catalog, now, random);
}

export function rotateState(raw, catalog, now = Date.now(), random = Math.random, force = false) {
  const state = normalizeState(raw, catalog);
  if (state.mode !== "rotate") return state;
  if (!force && now - state.lastRotate < state.intervalMs) return state;
  return advanceState(state, catalog, now, random);
}
