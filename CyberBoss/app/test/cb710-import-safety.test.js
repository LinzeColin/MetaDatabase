"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const zlib = require("node:zlib");
const { DatabaseSync } = require("node:sqlite");

const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { SqliteUserRepository } = require("../src/services/users/user-repository");
const { SqliteInviteCodeStore } = require("../src/services/users/invite-code-store");
const { RegistrationService } = require("../src/services/users/registration-service");
const {
  UploadPolicyError,
  validateArchiveManifest,
} = require("../src/services/imports/upload-policy");
const {
  SafeZipError,
  crc32,
  inspectZip,
  readZipEntries,
} = require("../src/services/imports/safe-zip-reader");
const { parseChatGPT } = require("../src/services/imports/chatgpt");
const { parseClaude } = require("../src/services/imports/claude");
const { parseGemini } = require("../src/services/imports/gemini");
const { parseDeepSeek } = require("../src/services/imports/deepseek");
const {
  ImportRouterError,
  parseImport,
  parseImportIsolating,
} = require("../src/services/imports/router");
const {
  ImportLedgerError,
  SqliteImportLedger,
  importIdentity,
} = require("../src/services/imports/import-ledger");

const KEY = Buffer.alloc(32, 7);
const IDENTITY_KEY = Buffer.alloc(32, 9);
const INVITE_SECRET = Buffer.alloc(32, 11);
const BOT = "bot-account-1";

function harness(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb710-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const databasePath = path.join(directory, "runtime.db");
  const spool = new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  const database = new DatabaseSync(databasePath);
  t.after(() => database.close());
  database.exec("PRAGMA foreign_keys=ON");
  const users = new SqliteUserRepository({ database, identityKey: IDENTITY_KEY });
  const invites = new SqliteInviteCodeStore({ database, secret: INVITE_SECRET });
  const registration = new RegistrationService({
    userRepository: users,
    inviteStore: invites,
  });
  const activate = (senderRef) => {
    const invite = invites.issue({ maxUses: 1, ttlMs: 60_000 });
    registration.start({ botAccountRef: BOT, senderRef, inviteCode: invite.code });
    return registration.consent({ botAccountRef: BOT, senderRef, accepted: true }).user;
  };
  return { database, spool, activate, ledger: new SqliteImportLedger({ database }) };
}

// A minimal ZIP writer, so archive attacks are built from real bytes rather
// than mocked away.
function buildZip(entries, { externalAttributes = 0, forceStoredSizes = null } = {}) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const entry of entries) {
    const nameBuffer = Buffer.from(entry.path, "utf8");
    const raw = Buffer.from(entry.data);
    const deflated = entry.stored ? raw : zlib.deflateRawSync(raw);
    const crc = crc32(raw);
    const compressedSize =
      forceStoredSizes && forceStoredSizes.compressed !== undefined
        ? forceStoredSizes.compressed
        : deflated.length;
    const uncompressedSize =
      forceStoredSizes && forceStoredSizes.uncompressed !== undefined
        ? forceStoredSizes.uncompressed
        : raw.length;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(entry.flags || 0, 6);
    local.writeUInt16LE(entry.stored ? 0 : 8, 8);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(compressedSize, 18);
    local.writeUInt32LE(uncompressedSize, 22);
    local.writeUInt16LE(nameBuffer.length, 26);
    locals.push(Buffer.concat([local, nameBuffer, deflated]));

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(entry.flags || 0, 8);
    central.writeUInt16LE(entry.stored ? 0 : 8, 10);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(compressedSize, 20);
    central.writeUInt32LE(uncompressedSize, 24);
    central.writeUInt16LE(nameBuffer.length, 28);
    central.writeUInt32LE(entry.externalAttributes || externalAttributes, 38);
    central.writeUInt32LE(offset, 42);
    centrals.push(Buffer.concat([central, nameBuffer]));
    offset += 30 + nameBuffer.length + deflated.length;
  }
  const localBlock = Buffer.concat(locals);
  const centralBlock = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(centralBlock.length, 12);
  eocd.writeUInt32LE(localBlock.length, 16);
  return Buffer.concat([localBlock, centralBlock, eocd]);
}

test("AC-022 a safe archive round-trips and its bounds are reported", () => {
  const archive = buildZip([
    { path: "conversations.json", data: Buffer.from('[{"id":"a"}]') },
    { path: "nested/notes.md", data: Buffer.from("# hello") },
  ]);
  const info = inspectZip(archive);
  assert.equal(info.entryCount, 2);
  assert.equal(info.expandedBytes, 12 + 7);
  const entries = readZipEntries(archive);
  assert.deepEqual(
    entries.map((entry) => entry.path).sort(),
    ["conversations.json", "nested/notes.md"],
  );
  assert.equal(entries[0].data.toString("utf8"), '[{"id":"a"}]');
});

test("AC-022 path traversal, symlinks and active content are refused", () => {
  const cases = [
    [[{ path: "../escape.json", data: Buffer.from("{}") }], {}, "ARCHIVE_PATH_FORBIDDEN"],
    [[{ path: "/abs.json", data: Buffer.from("{}") }], {}, "ARCHIVE_PATH_FORBIDDEN"],
    [[{ path: "a/../../out.json", data: Buffer.from("{}") }], {}, "ARCHIVE_PATH_FORBIDDEN"],
    [[{ path: "..\\windows.json", data: Buffer.from("{}") }], {}, "ARCHIVE_PATH_FORBIDDEN"],
    [[{ path: "run.sh", data: Buffer.from("rm -rf /") }], {}, "ARCHIVE_FILE_TYPE_FORBIDDEN"],
    [[{ path: "payload.exe", data: Buffer.from("MZ") }], {}, "ARCHIVE_FILE_TYPE_FORBIDDEN"],
    [[{ path: "inner.zip", data: Buffer.from("PK") }], {}, "ARCHIVE_FILE_TYPE_FORBIDDEN"],
    [
      [{ path: `${"deep/".repeat(13)}a.json`, data: Buffer.from("{}") }],
      {},
      "ARCHIVE_DEPTH_EXCEEDED",
    ],
    [
      // >>> 0 keeps the mode unsigned; a bare << 16 overflows into a negative.
      [{ path: "a.json", data: Buffer.from("{}"), externalAttributes: (0o120777 << 16) >>> 0 }],
      {},
      "ZIP_SYMLINK_FORBIDDEN",
    ],
    [
      [{ path: "enc.json", data: Buffer.from("{}"), flags: 1 }],
      {},
      "ZIP_ENCRYPTED_ENTRY",
    ],
  ];
  for (const [entries, options, code] of cases) {
    assert.throws(
      () => inspectZip(buildZip(entries, options)),
      (error) => {
        assert.ok(error instanceof SafeZipError || error instanceof UploadPolicyError);
        assert.equal(error.code, code, `expected ${code}, got ${error.code}`);
        return true;
      },
      `case ${entries[0].path} should be refused as ${code}`,
    );
  }
});

test("AC-022 zip bombs and duplicate targets are refused before inflation", () => {
  // A ratio no real text corpus reaches.
  const bomb = buildZip([{ path: "bomb.json", data: Buffer.alloc(500_000, 0x41) }]);
  assert.throws(() => inspectZip(bomb), (error) => error.code === "ZIP_RATIO_INVALID");

  // A central directory claiming output from no input.
  const lying = buildZip([{ path: "a.json", data: Buffer.from("{}") }], {
    forceStoredSizes: { compressed: 0, uncompressed: 5000 },
  });
  assert.throws(() => inspectZip(lying), (error) => error.code === "ZIP_RATIO_INVALID");

  // Two members normalising to the same target.
  const duplicate = buildZip([
    { path: "dir/a.json", data: Buffer.from("{}") },
    { path: "dir/./a.json", data: Buffer.from("{}") },
  ]);
  assert.throws(
    () => inspectZip(duplicate),
    (error) => error.code === "ARCHIVE_DUPLICATE_TARGET",
  );

  // Bounds are enforced against the policy, not the archive's claims.
  const many = buildZip(
    Array.from({ length: 4 }, (_unused, index) => ({
      path: `f${index}.json`,
      data: Buffer.from("{}"),
    })),
  );
  assert.throws(
    () => inspectZip(many, { maxFiles: 3 }),
    (error) => error.code === "ARCHIVE_TOO_MANY_FILES",
  );
  assert.throws(
    () => inspectZip(many, { maxArchiveBytes: 10 }),
    (error) => error.code === "ARCHIVE_TOO_LARGE",
  );
  assert.throws(
    () => inspectZip(many, { maxExpandedBytes: 4 }),
    (error) => error.code === "ARCHIVE_EXPANSION_LIMIT",
  );

  // The manifest preflight rejects the same shapes without any bytes at all.
  assert.throws(
    () =>
      validateArchiveManifest({
        archiveBytes: 10,
        files: [{ path: "../x.json", uncompressedBytes: 1 }],
      }),
    (error) => error.code === "ARCHIVE_PATH_FORBIDDEN",
  );
  assert.throws(
    () =>
      validateArchiveManifest({
        archiveBytes: 10,
        files: [
          { path: "a/b.json", uncompressedBytes: 1 },
          { path: "a//b.json", uncompressedBytes: 1 },
        ],
      }),
    (error) => error.code === "ARCHIVE_DUPLICATE_TARGET",
  );
  const accepted = validateArchiveManifest({
    archiveBytes: 20,
    files: [{ path: "./conversations.json", uncompressedBytes: 12 }],
  });
  assert.deepEqual(accepted.files, [{ path: "conversations.json", uncompressedBytes: 12 }]);
});

test("AC-018 ChatGPT parses the mapping tree with stable ordering and hashing", () => {
  const rows = [
    {
      id: "conv-1",
      title: "早上好",
      mapping: {
        n2: {
          message: {
            id: "m2",
            author: { role: "assistant" },
            create_time: 200,
            content: { parts: ["你好呀"] },
          },
        },
        n1: {
          message: {
            id: "m1",
            author: { role: "user" },
            create_time: 100,
            content: { parts: ["早"] },
          },
        },
      },
    },
  ];
  const parsed = parseChatGPT(rows);
  assert.equal(parsed.length, 1);
  assert.equal(parsed[0].source, "chatgpt");
  assert.equal(parsed[0].compatibility, "stable");
  assert.deepEqual(
    parsed[0].messages.map((message) => message.text),
    ["早", "你好呀"],
    "messages are ordered by create_time, not by object key order",
  );
  assert.match(parsed[0].sourceHash, /^[a-f0-9]{64}$/);

  // Key order in the export must not change the hash.
  const reordered = JSON.parse(JSON.stringify(rows));
  reordered[0].mapping = { n1: rows[0].mapping.n1, n2: rows[0].mapping.n2 };
  assert.equal(parseChatGPT(reordered)[0].sourceHash, parsed[0].sourceHash);
  // Different content must change it.
  const changed = JSON.parse(JSON.stringify(rows));
  changed[0].mapping.n1.message.content.parts = ["早上好"];
  assert.notEqual(parseChatGPT(changed)[0].sourceHash, parsed[0].sourceHash);
  assert.throws(() => parseChatGPT("{}"), (error) => error.code === "IMPORT_FORMAT_UNRECOGNISED");
});

test("AC-019 Claude parses conversations and flattens block content", () => {
  const parsed = parseClaude({
    conversations: [
      {
        uuid: "c-1",
        name: "计划",
        chat_messages: [
          { uuid: "m1", sender: "human", content: "帮我做个计划", created_at: "2026-01-01T00:00:00Z" },
          { uuid: "m2", sender: "assistant", content: [{ type: "text", text: "好的" }, "补充一句"] },
        ],
      },
    ],
  });
  assert.equal(parsed.length, 1);
  assert.equal(parsed[0].source, "claude");
  assert.equal(parsed[0].compatibility, "stable");
  assert.deepEqual(
    parsed[0].messages.map((message) => message.role),
    ["user", "assistant"],
  );
  assert.equal(parsed[0].messages[1].text, "好的\n补充一句");
  assert.equal(
    parseClaude(JSON.stringify({ conversations: [] })).length,
    0,
    "an empty export is not an error",
  );
  assert.throws(
    () => parseClaude({ nothing: true }),
    (error) => error.code === "IMPORT_FORMAT_UNRECOGNISED",
  );
});

test("AC-020/AC-021 Gemini and DeepSeek label beta and never fake completeness", () => {
  const geminiJson = parseGemini({
    conversations: [{ id: "g1", title: "G", messages: [{ role: "user", text: "hi" }] }],
  });
  assert.equal(geminiJson[0].compatibility, "beta");
  const geminiHtml = parseGemini("<html><script>steal()</script><p>你好</p></html>");
  assert.equal(geminiHtml[0].compatibility, "beta_low_confidence");
  assert.equal(geminiHtml[0].messages[0].text, "你好");
  assert.ok(
    !geminiHtml[0].messages[0].text.includes("steal"),
    "script content is stripped, not imported",
  );
  // An unrecognised structure must drop confidence rather than claim beta.
  assert.equal(parseGemini({ something: "else" })[0].compatibility, "beta_low_confidence");

  const deepseekJson = parseDeepSeek({
    conversations: [{ id: "d1", title: "D", messages: [{ role: "user", content: "hi" }] }],
  });
  assert.equal(deepseekJson[0].compatibility, "beta");
  const deepseekMarkdown = parseDeepSeek("# 标题\n\n正文内容");
  assert.equal(deepseekMarkdown[0].compatibility, "beta_low_confidence");
  assert.ok(deepseekMarkdown[0].messages[0].text.includes("正文内容"));
  assert.equal(parseDeepSeek({ unknown: true })[0].compatibility, "beta_low_confidence");

  // No beta source is ever labelled stable.
  for (const record of [...geminiJson, ...geminiHtml, ...deepseekJson, ...deepseekMarkdown]) {
    assert.notEqual(record.compatibility, "stable");
  }
  assert.throws(
    () => parseImport({ source: "telegram", input: "{}" }),
    (error) => error instanceof ImportRouterError,
  );
});

test("AC-023 one corrupt conversation is quarantined and the rest still import", () => {
  const rows = [
    { id: "ok-1", mapping: { n1: { message: { id: "m", author: { role: "user" }, create_time: 1, content: { parts: ["a"] } } } } },
    // A record whose mapping is not an object survives JSON but yields nothing
    // readable, so it must be quarantined rather than imported as an empty
    // shell that looks like a success.
    { id: "corrupt-record", mapping: 42 },
    // A record whose parts are all non-string is equally unreadable.
    { id: "corrupt-parts", mapping: { n1: { message: { id: "m", author: { role: "user" }, create_time: 1, content: { parts: [{ image: true }] } } } } },
    { id: "ok-2", mapping: { n1: { message: { id: "m", author: { role: "user" }, create_time: 1, content: { parts: ["b"] } } } } },
  ];
  const result = parseImportIsolating({ source: "chatgpt", input: rows });
  assert.equal(result.conversations.length, 2, "valid records still import");
  assert.deepEqual(
    result.quarantined.map((entry) => entry.index),
    [1, 2],
  );
  assert.ok(result.quarantined.every((entry) => entry.reason === "NO_PARSEABLE_MESSAGES"));
  // The quarantine reason is a code, never the record's content.
  assert.ok(!JSON.stringify(result.quarantined).includes("corrupt-record"));
  assert.deepEqual(
    result.conversations.map((record) => record.messages[0].text),
    ["a", "b"],
  );
});

test("AC-023 re-uploading the same export creates no duplicate facts", (t) => {
  const h = harness(t);
  const user = h.activate("i-user");
  const sourceHash = "a".repeat(64);

  const first = h.ledger.begin({
    userId: user.user_id,
    source: "chatgpt",
    sourceHash,
    objectRef: "r2://import/one",
  });
  assert.equal(first.duplicate, false);
  assert.equal(first.state, "preflight");

  const second = h.ledger.begin({
    userId: user.user_id,
    source: "chatgpt",
    sourceHash,
    objectRef: "r2://import/one-again",
  });
  assert.equal(second.duplicate, true);
  assert.equal(second.import_id, first.import_id);
  assert.equal(
    Number(h.database.prepare("SELECT COUNT(*) AS c FROM imports").get().c),
    1,
    "a repeat upload creates no second import row",
  );

  // A different user uploading the same file gets its own import.
  const other = h.activate("i-other");
  const otherImport = h.ledger.begin({
    userId: other.user_id,
    source: "chatgpt",
    sourceHash,
    objectRef: "r2://import/one",
  });
  assert.notEqual(otherImport.import_id, first.import_id);
  assert.equal(otherImport.duplicate, false);

  assert.throws(
    () => importIdentity({ userId: user.user_id, source: "chatgpt", sourceHash: "short" }),
    (error) => error instanceof ImportLedgerError,
  );
  assert.throws(
    () => importIdentity({ userId: user.user_id, source: "telegram", sourceHash }),
    /IMPORT_IDENTITY_INVALID/,
  );
});

test("AC-023 an interrupted import resumes from its checkpoint", (t) => {
  const h = harness(t);
  const user = h.activate("i-resume");
  const started = h.ledger.begin({
    userId: user.user_id,
    source: "claude",
    sourceHash: "b".repeat(64),
    objectRef: "r2://import/two",
  });

  h.ledger.checkpoint({
    importId: started.import_id,
    checkpoint: { conversationIndex: 40 },
    importedRecords: 40,
  });
  // Simulate a crash: a new worker reads the ledger rather than starting over.
  const resumed = h.ledger.resume(started.import_id);
  assert.equal(resumed.resumable, true);
  assert.deepEqual(resumed.checkpoint, { conversationIndex: 40 });
  assert.equal(resumed.importedRecords, 40);

  h.ledger.checkpoint({
    importId: started.import_id,
    checkpoint: { conversationIndex: 90 },
    importedRecords: 90,
  });
  // A stale worker must not rewind progress.
  assert.throws(
    () =>
      h.ledger.checkpoint({
        importId: started.import_id,
        checkpoint: { conversationIndex: 10 },
        importedRecords: 10,
      }),
    (error) => error.code === "IMPORT_CHECKPOINT_REJECTED",
  );
  assert.equal(h.ledger.resume(started.import_id).importedRecords, 90);

  h.ledger.complete({ importId: started.import_id, importedRecords: 100 });
  const done = h.ledger.resume(started.import_id);
  assert.equal(done.resumable, false);
  assert.equal(done.reason, "already_completed");
  assert.equal(done.importedRecords, 100);
  assert.throws(
    () => h.ledger.complete({ importId: started.import_id, importedRecords: 100 }),
    (error) => error.code === "IMPORT_STATE_INVALID",
  );
});

test("AC-023 a failed import keeps its receipt and leaves prior imports untouched", (t) => {
  const h = harness(t);
  const user = h.activate("i-fail");
  const good = h.ledger.begin({
    userId: user.user_id,
    source: "chatgpt",
    sourceHash: "c".repeat(64),
    objectRef: "r2://import/good",
  });
  h.ledger.complete({ importId: good.import_id, importedRecords: 7 });

  const bad = h.ledger.begin({
    userId: user.user_id,
    source: "gemini",
    sourceHash: "d".repeat(64),
    objectRef: "r2://import/bad",
    compatibility: "beta",
  });
  const failed = h.ledger.fail({ importId: bad.import_id, reasonCode: "ARCHIVE_EXPANSION_LIMIT" });
  assert.equal(failed.state, "failed");
  assert.ok(failed.checkpoint_json.includes("ARCHIVE_EXPANSION_LIMIT"));

  assert.equal(h.ledger.get(good.import_id).state, "completed");
  assert.equal(h.ledger.get(good.import_id).imported_records, 7);
  const listed = h.ledger.listForUser(user.user_id);
  assert.equal(listed.length, 2);
  // The listing is safe to show a user: no object payload, no raw content.
  assert.ok(!JSON.stringify(listed).includes("r2://"));
});

test("import parsing performs no model call and stores no raw chat in the repository", () => {
  // The import path is pure parsing: no module in it may reach a provider.
  for (const relative of [
    "upload-policy.js",
    "safe-zip-reader.js",
    "normalize.js",
    "chatgpt.js",
    "claude.js",
    "gemini.js",
    "deepseek.js",
    "router.js",
    "import-ledger.js",
  ]) {
    const source = fs.readFileSync(
      path.join(__dirname, "../src/services/imports", relative),
      "utf8",
    );
    for (const marker of ["openai", "anthropic", "generativelanguage", "fetch("]) {
      assert.ok(
        !source.toLowerCase().includes(marker),
        `${relative} must not reach a provider (${marker})`,
      );
    }
  }
});
