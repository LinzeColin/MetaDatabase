"use strict";

const OPEN_MODE = "COPY_INSTRUCTION_ONLY_NO_AUTO_OPEN";
const GREEN_STATUS = "GREEN_READY_FOR_OWNER_FINAL_ORDER";
const RED_STATUS = "RED_REVOKE_DO_NOT_ORDER";
const REQUIRED_TICKET_FIELDS = [
  "ticket_id",
  "provider_id",
  "event_id",
  "market_id",
  "selection_id",
  "parameters_sha256",
  "provider_contracts_sha256",
  "minimum_odds",
  "advice_expires_at",
  "risk_feature_required",
  "open_mode",
];
const REQUIRED_SNAPSHOT_FIELDS = [
  "provider_id",
  "event_id",
  "market_id",
  "selection_id",
  "current_odds",
  "observed_at",
  "risk_feature_enabled",
  "visible_fields_complete",
];

let localTicket = null;

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function isCanonicalOdds(value) {
  return typeof value === "string" && /^[1-9][0-9]*\.[0-9]{6}$/.test(value);
}

function isFixedOffsetTimestamp(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$/.test(value);
}

function isSha256(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function compareCanonicalOdds(left, right) {
  const [leftWhole, leftFraction] = left.split(".");
  const [rightWhole, rightFraction] = right.split(".");
  if (leftWhole.length !== rightWhole.length) {
    return leftWhole.length < rightWhole.length ? -1 : 1;
  }
  if (leftWhole !== rightWhole) {
    return leftWhole < rightWhole ? -1 : 1;
  }
  if (leftFraction === rightFraction) {
    return 0;
  }
  return leftFraction < rightFraction ? -1 : 1;
}

function validateTicket(ticket) {
  if (ticket === null || typeof ticket !== "object") {
    return false;
  }
  if (!REQUIRED_TICKET_FIELDS.every((field) => Object.prototype.hasOwnProperty.call(ticket, field))) {
    return false;
  }
  if (!["ticket_id", "provider_id", "event_id", "market_id", "selection_id"].every((field) => isNonEmptyString(ticket[field]))) {
    return false;
  }
  return (
    isCanonicalOdds(ticket.minimum_odds) &&
    isSha256(ticket.parameters_sha256) &&
    isSha256(ticket.provider_contracts_sha256) &&
    isFixedOffsetTimestamp(ticket.advice_expires_at) &&
    ticket.risk_feature_required === true &&
    ticket.open_mode === OPEN_MODE
  );
}

function validateSnapshot(snapshot) {
  if (snapshot === null || typeof snapshot !== "object") {
    return false;
  }
  if (!REQUIRED_SNAPSHOT_FIELDS.every((field) => Object.prototype.hasOwnProperty.call(snapshot, field))) {
    return false;
  }
  if (!["provider_id", "event_id", "market_id", "selection_id"].every((field) => isNonEmptyString(snapshot[field]))) {
    return false;
  }
  return (
    isCanonicalOdds(snapshot.current_odds) &&
    isFixedOffsetTimestamp(snapshot.observed_at) &&
    typeof snapshot.risk_feature_enabled === "boolean" &&
    typeof snapshot.visible_fields_complete === "boolean"
  );
}

function redResult(failedGateIds) {
  return {
    status: RED_STATUS,
    action: "DO_NOT_ORDER",
    verdict_zh: "红色撤销：至少一项即时校验失败，请勿下单。",
    failed_gate_ids: failedGateIds,
    automatic_platform_open_performed: false,
    order_submission_enabled: false,
  };
}

function evaluateVisibleSnapshot(ticket, snapshot) {
  if (!validateTicket(ticket)) {
    return redResult(["LOCAL_TICKET_UNAVAILABLE_OR_INVALID"]);
  }
  if (!validateSnapshot(snapshot)) {
    return redResult(["VISIBLE_FIELDS_UNAVAILABLE"]);
  }
  const failures = [];
  if (snapshot.visible_fields_complete !== true) failures.push("VISIBLE_FIELDS_UNAVAILABLE");
  if (snapshot.provider_id !== ticket.provider_id) failures.push("PROVIDER_IDENTITY_MISMATCH");
  if (snapshot.event_id !== ticket.event_id) failures.push("EVENT_IDENTITY_MISMATCH");
  if (snapshot.market_id !== ticket.market_id) failures.push("MARKET_IDENTITY_MISMATCH");
  if (snapshot.selection_id !== ticket.selection_id) failures.push("SELECTION_IDENTITY_MISMATCH");
  if (compareCanonicalOdds(snapshot.current_odds, ticket.minimum_odds) < 0) failures.push("CURRENT_ODDS_BELOW_MINIMUM");
  if (snapshot.observed_at.slice(-6) !== ticket.advice_expires_at.slice(-6) || snapshot.observed_at >= ticket.advice_expires_at) failures.push("ADVICE_EXPIRED");
  if (snapshot.risk_feature_enabled !== true) failures.push("RISK_FEATURE_DISABLED");
  if (failures.length > 0) return redResult(failures);
  return {
    status: GREEN_STATUS,
    action: "OWNER_FINAL_ORDER_MANUAL_ONLY",
    verdict_zh: "绿色：即时校验通过；仅由你自行完成最终下单。",
    failed_gate_ids: [],
    automatic_platform_open_performed: false,
    order_submission_enabled: false,
  };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message === null || typeof message !== "object") {
    sendResponse(redResult(["MALFORMED_COMPANION_MESSAGE"]));
    return;
  }
  if (message.type === "ABD_SET_LOCAL_TICKET") {
    localTicket = validateTicket(message.ticket) ? Object.freeze({ ...message.ticket }) : null;
    sendResponse({
      status: localTicket === null ? RED_STATUS : "LOCAL_TICKET_ACCEPTED_NO_NETWORK",
      automatic_platform_open_performed: false,
      order_submission_enabled: false,
    });
    return;
  }
  if (message.type === "ABD_VISIBLE_QUOTE_SNAPSHOT") {
    sendResponse(evaluateVisibleSnapshot(localTicket, message.snapshot));
    return;
  }
  sendResponse(redResult(["UNKNOWN_COMPANION_MESSAGE"]));
});

chrome.action.onClicked.addListener((tab) => {
  if (typeof tab.id !== "number") return;
  chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] }).catch(() => undefined);
});
