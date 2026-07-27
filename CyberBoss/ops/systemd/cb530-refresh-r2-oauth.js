#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const OAUTH_CLIENT_ID = "54d11594-84e4-41aa-b438-e81b8fa78ee7";
const OAUTH_TOKEN_URL = "https://dash.cloudflare.com/oauth2/token";
const TOKEN_PATTERN = /^[A-Za-z0-9._~-]{20,256}$/;
const REFRESH_PATTERN = /^[A-Za-z0-9._~-]{20,4096}$/;
const PRODUCTION_ROOTS = Object.freeze({ state: "/var/lib/cyberboss", runtime: "/run" });

class R2OauthRefreshError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

async function refreshR2Oauth({ environment = process.env, fetchImpl = globalThis.fetch, roots = PRODUCTION_ROOTS } = {}) {
  if (typeof fetchImpl !== "function") {
    throw new R2OauthRefreshError("CB530_R2_OAUTH_FETCH_UNAVAILABLE");
  }
  const stateRoot = String(roots?.state || "");
  const runtimeRoot = String(roots?.runtime || "");
  if (!path.isAbsolute(stateRoot) || !path.isAbsolute(runtimeRoot)) {
    throw new R2OauthRefreshError("CB530_R2_OAUTH_ROOTS_INVALID");
  }
  const stateDir = managedPath(environment.CB_R2_OAUTH_STATE_DIR, stateRoot, "CB530_R2_OAUTH_STATE_DIR_INVALID");
  const bootstrapFile = managedPath(environment.CB_R2_OAUTH_REFRESH_TOKEN_FILE, runtimeRoot, "CB530_R2_OAUTH_REFRESH_FILE_INVALID");
  const runtimeTokenFile = managedPath(environment.CB_R2_TOKEN_FILE, runtimeRoot, "CB530_R2_OAUTH_RUNTIME_FILE_INVALID");
  ensurePrivateDirectory(stateDir);

  const persistedRefreshFile = path.join(stateDir, "r2_oauth_refresh_token");
  const refreshToken = fs.existsSync(persistedRefreshFile)
    ? readSecret(persistedRefreshFile, REFRESH_PATTERN, "CB530_R2_OAUTH_STATE_INVALID")
    : readSecret(bootstrapFile, REFRESH_PATTERN, "CB530_R2_OAUTH_REFRESH_FILE_INVALID");
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: refreshToken,
    client_id: OAUTH_CLIENT_ID,
  });

  let response;
  try {
    response = await fetchImpl(OAUTH_TOKEN_URL, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });
  } catch {
    throw new R2OauthRefreshError("CB530_R2_OAUTH_REFRESH_FAILED");
  }
  if (!response || response.ok !== true) {
    throw new R2OauthRefreshError("CB530_R2_OAUTH_REFRESH_FAILED");
  }
  let result;
  try {
    result = await response.json();
  } catch {
    throw new R2OauthRefreshError("CB530_R2_OAUTH_RESPONSE_INVALID");
  }
  const accessToken = String(result?.access_token || "");
  const nextRefreshToken = String(result?.refresh_token || refreshToken);
  const expiresIn = Number(result?.expires_in);
  if (!TOKEN_PATTERN.test(accessToken) || !REFRESH_PATTERN.test(nextRefreshToken) || !Number.isInteger(expiresIn) || expiresIn < 60 || expiresIn > 31_536_000) {
    throw new R2OauthRefreshError("CB530_R2_OAUTH_RESPONSE_INVALID");
  }

  if (nextRefreshToken !== refreshToken || !fs.existsSync(persistedRefreshFile)) {
    writeSecret(persistedRefreshFile, nextRefreshToken);
  }
  writeSecret(runtimeTokenFile, accessToken);
  return Object.freeze({
    status: "passed",
    code: "CB530_R2_OAUTH_REFRESHED",
    expires_in_seconds: expiresIn,
    refresh_token_rotated: nextRefreshToken !== refreshToken,
  });
}

function managedPath(value, root, code) {
  const candidate = String(value || "");
  if (!path.isAbsolute(candidate) || candidate.includes("\0")) {
    throw new R2OauthRefreshError(code);
  }
  const resolved = path.resolve(candidate);
  const boundary = path.resolve(root);
  if (resolved !== boundary && !resolved.startsWith(`${boundary}${path.sep}`)) {
    throw new R2OauthRefreshError(code);
  }
  return resolved;
}

function ensurePrivateDirectory(directory) {
  try {
    fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
    fs.chmodSync(directory, 0o700);
    const stats = fs.lstatSync(directory);
    if (!stats.isDirectory() || stats.isSymbolicLink()) {
      throw new Error("not_directory");
    }
  } catch {
    throw new R2OauthRefreshError("CB530_R2_OAUTH_STATE_DIR_INVALID");
  }
}

function readSecret(filePath, pattern, code) {
  try {
    const stats = fs.lstatSync(filePath);
    if (!stats.isFile() || stats.isSymbolicLink()) {
      throw new Error("not_regular");
    }
    const value = fs.readFileSync(filePath, "utf8").trim();
    if (!pattern.test(value)) {
      throw new Error("shape");
    }
    return value;
  } catch {
    throw new R2OauthRefreshError(code);
  }
}

function writeSecret(filePath, value) {
  const target = path.resolve(filePath);
  const parent = path.dirname(target);
  ensureWritableDirectory(parent);
  const temporary = path.join(parent, `.${path.basename(target)}.${crypto.randomUUID()}.tmp`);
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(descriptor, `${value}\n`, "utf8");
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    fs.renameSync(temporary, target);
    fs.chmodSync(target, 0o600);
    fsyncDirectory(parent);
  } catch {
    if (typeof descriptor === "number") {
      fs.closeSync(descriptor);
    }
    throw new R2OauthRefreshError("CB530_R2_OAUTH_STATE_WRITE_FAILED");
  }
}

function ensureWritableDirectory(directory) {
  try {
    const stats = fs.lstatSync(directory);
    if (!stats.isDirectory() || stats.isSymbolicLink()) {
      throw new Error("not_directory");
    }
  } catch {
    throw new R2OauthRefreshError("CB530_R2_OAUTH_STATE_WRITE_FAILED");
  }
}

function fsyncDirectory(directory) {
  let descriptor;
  try {
    descriptor = fs.openSync(directory, "r");
    fs.fsyncSync(descriptor);
  } finally {
    if (typeof descriptor === "number") {
      fs.closeSync(descriptor);
    }
  }
}

if (require.main === module) {
  refreshR2Oauth().then(
    (result) => process.stdout.write(`${JSON.stringify(result)}\n`),
    (error) => {
      const code = error instanceof R2OauthRefreshError ? error.code : "CB530_R2_OAUTH_REFRESH_FAILED";
      process.stderr.write(`${JSON.stringify({ status: "failed", code })}\n`);
      process.exitCode = 2;
    },
  );
}

module.exports = { R2OauthRefreshError, refreshR2Oauth };
