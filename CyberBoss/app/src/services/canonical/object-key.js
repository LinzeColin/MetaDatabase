"use strict";

// CB-800 / AC-029, AC-030: object naming for the R2 encrypted-object area.
//
// Two properties matter and both are load-bearing for deletion:
//   1. every object a user owns sits under one prefix, so a scoped delete can
//      enumerate the whole set without consulting a second index that could
//      itself be incomplete;
//   2. no segment can escape that prefix, so one user's key can never name
//      another user's object.
//
// The version suffix makes an object immutable: a new version writes a new
// key rather than overwriting, which is what "repoint object version" in the
// CB-800 rollback plan depends on.

const { createHash } = require("node:crypto");

const ROOT = "cyberboss/users";
const SEGMENT_PATTERN = /^[A-Za-z0-9_-]{1,80}$/;
const CATEGORIES = Object.freeze([
  "import",
  "export",
  "attachment",
  "snapshot",
  "profile",
  "timeline",
]);

class ObjectKeyError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "ObjectKeyError";
    this.code = code;
    this.detail = detail;
  }
}

function safeSegment(value, field) {
  const text = String(value ?? "");
  if (!SEGMENT_PATTERN.test(text)) {
    throw new ObjectKeyError("OBJECT_SEGMENT_INVALID", field);
  }
  // Belt and braces: the pattern already excludes these, but a future edit to
  // the pattern must not silently reopen traversal.
  if (text.includes("..") || text.includes("/") || text.includes("\\")) {
    throw new ObjectKeyError("OBJECT_SEGMENT_TRAVERSAL", field);
  }
  return text;
}

function userObjectPrefix(userId) {
  return `${ROOT}/${safeSegment(userId, "userId")}/`;
}

function userObjectKey({ userId, category, objectId, version = 1 }) {
  const uid = safeSegment(userId, "userId");
  const kind = safeSegment(category, "category");
  if (!CATEGORIES.includes(kind)) {
    throw new ObjectKeyError("OBJECT_CATEGORY_NOT_ALLOWED", "category");
  }
  const oid = safeSegment(objectId, "objectId");
  if (!Number.isInteger(version) || version < 1 || version > 1_000_000) {
    throw new ObjectKeyError("OBJECT_VERSION_INVALID", "version");
  }
  const digest = createHash("sha256")
    .update(`${uid}\u0000${kind}\u0000${oid}\u0000${version}`)
    .digest("hex");
  return `${ROOT}/${uid}/${kind}/${oid}/v${version}-${digest.slice(0, 16)}.bin`;
}

// A key belongs to a user only if it sits under that user's prefix. Used by
// export and delete so neither can touch a neighbouring scope.
function keyBelongsToUser(key, userId) {
  if (typeof key !== "string" || key.length === 0) {
    return false;
  }
  return key.startsWith(userObjectPrefix(userId));
}

function assertKeyBelongsToUser(key, userId) {
  if (!keyBelongsToUser(key, userId)) {
    throw new ObjectKeyError("OBJECT_KEY_SCOPE_VIOLATION", "key");
  }
  return key;
}

// Rollback support: name the previous version of the same logical object.
function previousVersionKey({ userId, category, objectId, version }) {
  if (!Number.isInteger(version) || version <= 1) {
    throw new ObjectKeyError("OBJECT_NO_PREVIOUS_VERSION", "version");
  }
  return userObjectKey({ userId, category, objectId, version: version - 1 });
}

module.exports = {
  CATEGORIES,
  ROOT,
  ObjectKeyError,
  assertKeyBelongsToUser,
  keyBelongsToUser,
  previousVersionKey,
  safeSegment,
  userObjectKey,
  userObjectPrefix,
};
