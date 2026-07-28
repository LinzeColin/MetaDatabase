"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  CANONICAL,
  FORBIDDEN_PHRASES,
  USER_ACTIONS,
  resolveNoviceCommand,
} = require("../src/services/commands/novice-command-map");
const {
  JARGON,
  MESSAGES,
  auditMessages,
  present,
} = require("../src/services/ops/novice-presenter");
const {
  OWNER_ONLY_CAPABILITIES,
} = require("../src/services/users/user-context");
const { ACTION_ALLOWLIST } = require("../src/services/portal/setup-portal");

const PORTAL = fs.readFileSync(
  path.join(__dirname, "../templates/setup-portal.html"),
  "utf8",
);

test("AC-037 natural Chinese resolves to frozen actions without a model", () => {
  const cases = [
    ["开始", "onboarding.start"],
    ["我要开始", "onboarding.start"],
    ["怎么开始？", "onboarding.start"],
    ["同意并开始", "onboarding.consent"],
    ["连接我的AI", "portal.provider"],
    ["  导入聊天  ", "portal.import"],
    ["你记得我什么", "portal.memory"],
    ["最近七天", "analytics.week"],
    ["别再问我", "checkin.disable"],
    ["删除我的数据。", "privacy.delete"],
    ["还能用多少", "usage.remaining"],
    ["停", "turn.stop"],
  ];
  for (const [text, action] of cases) {
    assert.equal(resolveNoviceCommand(text), action, `${text} should map to ${action}`);
  }
  // Resolution is a table lookup, so it is stable and free.
  assert.deepEqual(
    cases.map(([text]) => resolveNoviceCommand(text)),
    cases.map(([, action]) => action),
  );
  assert.equal(resolveNoviceCommand(""), null);
  assert.equal(resolveNoviceCommand("今天天气怎么样"), null, "ordinary chat is not a command");
});

test("AC-037 no novice phrase can reach an Owner capability", () => {
  for (const phrase of FORBIDDEN_PHRASES) {
    assert.equal(
      resolveNoviceCommand(phrase),
      null,
      `${phrase} must not resolve to any action`,
    );
    assert.equal(resolveNoviceCommand(`请帮我${phrase}`), null);
  }
  // The user action set is disjoint from the Owner-only capability set.
  for (const action of USER_ACTIONS) {
    assert.ok(
      !OWNER_ONLY_CAPABILITIES.includes(action),
      `${action} appears in the Owner-only set`,
    );
  }
  // The portal allowlist governs mutating requests only. Navigation intents
  // ("open my profile") are reads and correctly have no mutating entry; every
  // intent that does change state must map onto the frozen allowlist.
  const MUTATING_INTENTS = Object.freeze({
    "privacy.export": "privacy.export",
    "privacy.delete": "privacy.delete",
  });
  for (const [intent, action] of Object.entries(MUTATING_INTENTS)) {
    assert.ok(USER_ACTIONS.includes(intent), `${intent} is missing from the command map`);
    assert.ok(
      ACTION_ALLOWLIST.includes(action),
      `${intent} has no matching portal allowlist entry`,
    );
  }
  // Nothing in the allowlist itself is an Owner capability.
  for (const action of ACTION_ALLOWLIST) {
    assert.ok(!OWNER_ONLY_CAPABILITIES.includes(action), `${action} is Owner-only`);
  }
});

test("AC-037/AC-049 every message is Chinese, jargon-free and repairable", () => {
  const audit = auditMessages();
  assert.deepEqual(audit.problems, [], "no message may leak jargon or lack a repair action");
  assert.ok(audit.messageCount >= 15);

  for (const [key, entry] of Object.entries(MESSAGES)) {
    assert.match(entry.text, /[一-龥]/, `${key} must be Chinese`);
    for (const word of JARGON) {
      assert.ok(!entry.text.toLowerCase().includes(word), `${key} leaks ${word}`);
    }
  }
  // A budget block explains what happened and exactly one thing to do.
  const blocked = present("budget_exhausted");
  assert.equal(blocked.requiresRepairAction, true);
  assert.equal(blocked.primaryAction, "设置");
  assert.match(blocked.text, /明天会自动恢复/);
  // Usage protection is visible before anything goes wrong.
  assert.match(present("usage_remaining", { remaining_percent: 72 }).text, /72/);
  assert.throws(() => present("no_such_message"), /MESSAGE_NOT_DEFINED/);
});

test("AC-049 the setup page is mobile-first with one primary action per view", () => {
  // One primary action per visible view.
  const primaries = PORTAL.match(/class="primary"/g) || [];
  const sections = PORTAL.match(/<section id="view-[a-z]+"/g) || [];
  assert.equal(
    primaries.length,
    sections.length,
    "each view carries exactly one primary action",
  );
  const visibleSections = (PORTAL.match(/<section id="view-[a-z]+"(?! hidden)/g) || []).length;
  assert.equal(visibleSections, 1, "only one view is visible at a time");

  // Touch target, base font and viewport.
  assert.match(PORTAL, /--touch:\s*44px/);
  assert.match(PORTAL, /min-height:\s*var\(--touch\)/);
  assert.match(PORTAL, /font:\s*16px/);
  assert.match(PORTAL, /font-size:\s*16px/);
  assert.match(PORTAL, /width=device-width, initial-scale=1/);
  assert.match(PORTAL, /overflow-x:\s*hidden/);
  assert.match(PORTAL, /overflow-wrap:\s*anywhere/);

  // Keyboard operability and an error that always carries a repair button.
  assert.match(PORTAL, /:focus-visible/);
  assert.match(PORTAL, /id="error-repair"/);
  assert.match(PORTAL, /<label for="provider">/);
  assert.match(PORTAL, /<label for="apikey">/);
  assert.match(PORTAL, /<label for="archive">/);

  // Chinese only in user-visible copy: no English sentences in the body text.
  const bodyText = PORTAL.replace(/<script[\s\S]*?<\/script>/g, "")
    .replace(/<style[\s\S]*?<\/style>/g, "")
    .replace(/<[^>]+>/g, " ");
  assert.match(bodyText, /[一-龥]/);
  assert.ok(
    !/\b(?:Please|Submit|Continue|Settings|Error)\b/.test(bodyText),
    "user-visible copy must be Chinese",
  );
  assert.match(PORTAL, /<html lang="zh-CN">/);
});

test("AC-049 the setup page is locked down and leaks no token", () => {
  // Strict CSP with no unsafe-inline and no remote origins.
  assert.match(PORTAL, /Content-Security-Policy/);
  assert.match(PORTAL, /default-src 'none'/);
  assert.match(PORTAL, /base-uri 'none'/);
  assert.match(PORTAL, /object-src 'none'/);
  assert.match(PORTAL, /frame-ancestors 'none'/);
  assert.ok(!PORTAL.includes("unsafe-inline"), "no unsafe-inline");
  assert.ok(!PORTAL.includes("unsafe-eval"), "no unsafe-eval");
  assert.ok(!/https?:\/\/(?!schema)/.test(PORTAL.replace(/xmlns[^"]*"[^"]*"/g, "")),
    "no remote origin is referenced");

  // No inline event handlers and no unsafe HTML sinks.
  assert.ok(!/\son[a-z]+=/i.test(PORTAL), "no inline event handlers");
  for (const sink of ["innerHTML", "outerHTML", "document.write", "eval("]) {
    assert.ok(!PORTAL.includes(sink), `no ${sink}`);
  }
  // No inline style attributes: styling is all nonce-guarded CSS.
  assert.ok(!/<[^>]+\sstyle="/.test(PORTAL), "no inline style attributes");

  // The one-time token is stripped from the address bar and never re-sent.
  assert.match(PORTAL, /location\.hash/);
  assert.match(PORTAL, /history\.replaceState/);
  assert.match(PORTAL, /<meta name="referrer" content="no-referrer">/);
  assert.ok(!PORTAL.includes("location.search"), "the token is never read from the query");
});

test("AC-004/AC-010 the page states the one-time rule and auto-save in Chinese", () => {
  assert.match(PORTAL, /只能用一次/);
  assert.match(PORTAL, /自动保存/);
  assert.match(present("link_expired").text, /只能用一次/);
  assert.equal(present("link_expired").primaryAction, "设置");
  assert.equal(present("session_expired").requiresRepairAction, true);
  // Consent copy names the exact action that activates.
  assert.match(present("consent").text, /同意并开始/);
  assert.equal(present("consent").primaryAction, "同意并开始");
});

test("AC-049 the novice path requires zero command-line steps", () => {
  const surfaces = [
    fs.readFileSync(path.join(__dirname, "../src/services/commands/novice-command-map.js"), "utf8"),
    fs.readFileSync(path.join(__dirname, "../src/services/ops/novice-presenter.js"), "utf8"),
    PORTAL,
  ];
  for (const source of surfaces) {
    for (const marker of ["sudo ", "systemctl ", "npm install", "curl -", "ssh "]) {
      assert.ok(
        !source.includes(marker),
        `a novice surface must not instruct a shell step (${marker})`,
      );
    }
  }
  // Every entry a novice needs is reachable by a Chinese phrase.
  for (const need of ["portal.provider", "portal.import", "portal.profile", "privacy.export", "privacy.delete", "usage.remaining"]) {
    assert.ok(CANONICAL[need] && CANONICAL[need].length > 0, `${need} has no Chinese phrase`);
    assert.equal(resolveNoviceCommand(CANONICAL[need][0]), need);
  }
});
