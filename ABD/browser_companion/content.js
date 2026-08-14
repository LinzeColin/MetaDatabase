"use strict";

const VISIBLE_FIELDS = [
  "provider_id",
  "event_id",
  "market_id",
  "selection_id",
  "current_odds",
  "observed_at",
  "risk_feature_enabled",
];

function readVisibleField(name) {
  const node = document.querySelector(`[data-abd-visible-field="${name}"]`);
  if (node === null) return null;
  const text = (node.innerText || node.textContent || "").trim();
  return text.length > 0 ? text : null;
}

function readBooleanField(name) {
  const value = readVisibleField(name);
  if (value === "true") return true;
  if (value === "false") return false;
  return null;
}

const fields = Object.fromEntries(
  VISIBLE_FIELDS.map((name) => [name, name === "risk_feature_enabled" ? readBooleanField(name) : readVisibleField(name)]),
);
const complete = Object.values(fields).every((value) => value !== null);
const snapshot = {
  provider_id: fields.provider_id || "UNKNOWN_VISIBLE_PROVIDER",
  event_id: fields.event_id || "UNKNOWN_VISIBLE_EVENT",
  market_id: fields.market_id || "UNKNOWN_VISIBLE_MARKET",
  selection_id: fields.selection_id || "UNKNOWN_VISIBLE_SELECTION",
  current_odds: fields.current_odds || "1.000000",
  observed_at: fields.observed_at || "1970-01-01T00:00:00+00:00",
  risk_feature_enabled: fields.risk_feature_enabled === true,
  visible_fields_complete: complete,
};

chrome.runtime.sendMessage({ type: "ABD_VISIBLE_QUOTE_SNAPSHOT", snapshot });
