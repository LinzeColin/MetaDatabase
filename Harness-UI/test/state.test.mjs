import assert from "node:assert/strict";
import test from "node:test";
import { nextState, normalizeState, patchState, rotateState } from "../src/state.mjs";

const catalog = { entries: [{ id: "one" }, { id: "two" }, { id: "three" }] };

test("normalizes selected and hidden entries against the current catalog", () => {
  const state = normalizeState({ selected: "missing", hidden: ["two", "missing", "two"] }, catalog);
  assert.equal(state.selected, null);
  assert.deepEqual(state.hidden, ["two"]);
});

test("patches only public state fields", () => {
  const state = patchState({}, { selected: "one", unexpected: "no" }, catalog, 42);
  assert.equal(state.selected, "one");
  assert.equal(state.updated, 42);
  assert.equal(state.unexpected, undefined);
});

test("rotates through a complete cycle before refilling", () => {
  let state = normalizeState({ mode: "rotate" }, catalog);
  const seen = [];
  for (let index = 0; index < 3; index += 1) {
    state = rotateState(state, catalog, index + 1, () => 0, true);
    seen.push(state.selected);
  }
  assert.equal(new Set(seen).size, 3);
});

test("next advances immediately without changing gallery mode", () => {
  const state = nextState({ mode: "gallery", selected: "one", cycle: ["one", "two", "three"], cursor: 0 }, catalog, 42);
  assert.equal(state.mode, "gallery");
  assert.equal(state.selected, "two");
  assert.equal(state.cursor, 2);
  assert.equal(state.lastRotate, 42);
  assert.equal(state.updated, 42);
});
