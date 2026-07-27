"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { R2OauthRefreshError, refreshR2Oauth } = require("../cb530-refresh-r2-oauth");

const INITIAL_REFRESH = "r".repeat(93);
const NEXT_REFRESH = "n".repeat(93);
const ACCESS_TOKEN = "a".repeat(93);

function setup(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cb530-oauth-"));
  const runRoot = path.join(root, "run");
  const stateRoot = path.join(root, "var", "lib", "cyberboss", "credentials");
  fs.mkdirSync(runRoot, { recursive: true, mode: 0o700 });
  fs.writeFileSync(path.join(runRoot, "refresh"), `${INITIAL_REFRESH}\n`, { mode: 0o600 });
  t.after(() => fs.rmSync(root, { force: true, recursive: true }));
  return {
    environment: {
      CB_R2_OAUTH_STATE_DIR: stateRoot,
      CB_R2_OAUTH_REFRESH_TOKEN_FILE: path.join(runRoot, "refresh"),
      CB_R2_TOKEN_FILE: path.join(runRoot, "r2_api_token"),
    },
    runRoot,
    stateRoot,
    roots: { state: path.join(root, "var", "lib", "cyberboss"), runtime: runRoot },
  };
}

test("CB-530 OAuth refresh writes a short-lived R2 access token and preserves no token in its receipt", async (t) => {
  const fixture = setup(t);
  let request;
  const result = await refreshR2Oauth({
    environment: fixture.environment,
    roots: fixture.roots,
    fetchImpl: async (_url, options) => {
      request = options;
      return { ok: true, json: async () => ({ access_token: ACCESS_TOKEN, refresh_token: NEXT_REFRESH, expires_in: 3600 }) };
    },
  });

  assert.equal(request.method, "POST");
  assert.match(request.body, /grant_type=refresh_token/);
  assert.equal(fs.readFileSync(path.join(fixture.runRoot, "r2_api_token"), "utf8"), `${ACCESS_TOKEN}\n`);
  assert.equal(fs.readFileSync(path.join(fixture.stateRoot, "r2_oauth_refresh_token"), "utf8"), `${NEXT_REFRESH}\n`);
  assert.deepEqual(result, {
    status: "passed",
    code: "CB530_R2_OAUTH_REFRESHED",
    expires_in_seconds: 3600,
    refresh_token_rotated: true,
  });
  assert.equal(JSON.stringify(result).includes(ACCESS_TOKEN), false);
  assert.equal(JSON.stringify(result).includes(NEXT_REFRESH), false);
});

test("CB-530 OAuth refresh fails closed without writing an access token", async (t) => {
  const fixture = setup(t);
  await assert.rejects(
    () => refreshR2Oauth({
      environment: fixture.environment,
      roots: fixture.roots,
      fetchImpl: async () => ({ ok: false, json: async () => ({}) }),
    }),
    (error) => error instanceof R2OauthRefreshError && error.code === "CB530_R2_OAUTH_REFRESH_FAILED",
  );
  assert.equal(fs.existsSync(path.join(fixture.runRoot, "r2_api_token")), false);
});
