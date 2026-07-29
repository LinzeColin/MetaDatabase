function newIdempotencyKey() {
  // `randomUUID` is available on the HTTPS production surface. Keep a
  // collision-resistant-enough fallback for embedded and test contexts where
  // the Web Crypto secure-context gate is unavailable; this is a request
  // de-duplication token, never an authentication or encryption secret.
  return globalThis.crypto?.randomUUID?.() || `client_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

export class AccountApi {
  constructor(base = "/api/platform/v1") { this.base = base; this.csrf = ""; }
  readiness() { return fetch("/readyz", { credentials: "same-origin", headers: { Accept: "application/json" } }).then(async response => ({ ok: response.ok, status: response.status, payload: await response.json().catch(() => ({})) })); }
  async session() { const data = await this.request("/session", { allow401: true }); if (data?.csrf) this.csrf = data.csrf; return data; }
  async registerPassword(input) { return this.auth("/auth/register/password", input); }
  async loginPassword(input) { return this.auth("/auth/login/password", input); }
  async registerWeRead(input) { return this.auth("/auth/register/weread", input); }
  async loginWeRead(input) { return this.auth("/auth/login/weread", input); }
  async logout() { const value = await this.request("/auth/logout", { method: "POST", body: {} }); this.csrf = ""; return value; }
  async auth(path, input) { const data = await this.request(path, { method: "POST", body: input, authless: true }); this.csrf = data.csrf || ""; return data; }
  async oauth(provider, intent = "login") { const data = await this.request(`/oauth/${provider}/start?intent=${encodeURIComponent(intent)}`); location.assign(data.authorizationUrl); }
  profile() { return this.request("/profile"); }
  updateProfile(input) { return this.request("/profile", { method: "PATCH", body: input }); }
  consent() { return this.request("/consent"); }
  updateConsent(input) { return this.request("/consent", { method: "PATCH", body: input }); }
  aiPreferences() { return this.request("/ai/preferences"); }
  updateAiPreferences(input) { return this.request("/ai/preferences", { method: "PATCH", body: input }); }
  aiInquiries(limit = 100) { return this.request(`/ai/inquiries?limit=${encodeURIComponent(Math.min(Math.max(Number(limit) || 100, 1), 500))}`); }
  recordAiInquiry(input) { return this.request("/ai/inquiries", { method: "POST", body: input }); }
  bindWeRead(key) { return this.request("/auth/link/weread", { method: "POST", body: { key } }); }
  rotateWeRead(key) { return this.request("/auth/rotate/weread", { method: "POST", body: { key } }); }
  reauthPassword(password) { return this.request("/auth/reauth/password", { method: "POST", body: { password } }); }
  reauthWeRead(key) { return this.request("/auth/reauth/weread", { method: "POST", body: { key } }); }
  configurePassword(input) { return this.request("/account/password", { method: "POST", body: input }); }
  sessions() { return this.request("/account/sessions"); }
  revokeSession(id) { return this.request(`/account/sessions/${encodeURIComponent(id)}`, { method: "DELETE", body: {} }); }
  revokeOtherSessions() { return this.request("/account/sessions/revoke-others", { method: "POST", body: {} }); }
  notes(limit = 5_000) { return this.request(`/notes?limit=${encodeURIComponent(Math.min(Math.max(Number(limit) || 200, 1), 5_000))}`); }
  note(id) { return this.request(`/notes/${encodeURIComponent(id)}`); }
  exportNotes(ids) { return this.request("/notes/export", { method: "POST", body: { ids } }); }
  saveNote(note) { return this.request("/notes", { method: "POST", body: note }); }
  deleteNote(id, expectedVersion) { return this.request(`/notes/${encodeURIComponent(id)}?expectedVersion=${encodeURIComponent(expectedVersion)}`, { method: "DELETE", body: {} }); }
  syncPull(cursor = 0) { return this.request("/sync/pull", { method: "POST", body: { cursor, limit: 500 } }); }
  syncPush(operations) { return this.request("/sync/push", { method: "POST", body: { operations } }); }
  wereadSync(mode = "auto") { return this.request("/weread/sync", { method: "POST", body: { mode, recommendationPages: 3 }, headers: { "Idempotency-Key": newIdempotencyKey() } }); }
  wereadSyncJob(id) { return this.request(`/weread/sync/jobs/${encodeURIComponent(id)}`); }
  providerItems(provider, params = {}) { const query = new URLSearchParams(params); return this.request(`/imports/${provider}/items?${query}`); }
  startImport(provider, selection) { return this.request(`/imports/${provider}/start`, { method: "POST", body: { selection }, headers: { "Idempotency-Key": newIdempotencyKey() } }); }
  importJob(id) { return this.request(`/imports/jobs/${encodeURIComponent(id)}`); }
  analytics() { return this.request("/analytics/dashboard"); }
  exportWeRead() { return this.request("/weread/export"); }
  exportAccount() { return this.request("/account/export"); }
  deleteAccount() { return this.request("/account/delete", { method: "POST", body: {} }); }
  businessLines() { return this.request("/status/business-lines"); }
  adminOverview() { return this.request("/admin/overview", { method: "POST", body: {} }); }
  adminAccounts({ reason, query = "", limit = 100 }) { return this.request("/admin/accounts", { method: "POST", body: { reason, query, limit } }); }
  adminNotes({ reason, accountId = "", limit = 100 }) { return this.request("/admin/notes", { method: "POST", body: { reason, accountId, limit } }); }
  adminNote(id, reason) { return this.request(`/admin/notes/${encodeURIComponent(id)}`, { method: "POST", body: { reason } }); }
  adminPrompts({ reason, limit = 100 }) { return this.request("/admin/prompts", { method: "POST", body: { reason, limit } }); }
  adminAudit({ reason, limit = 100 }) { return this.request("/admin/audit", { method: "POST", body: { reason, limit } }); }

  async request(path, { method = "GET", body, headers = {}, allow401 = false } = {}) {
    // Bypass any response cached before the account API adopted no-store headers.
    // Sync coverage must always be read from the current server state.
    const init = { method, credentials: "include", cache: "no-store", headers: { Accept: "application/json", ...headers } };
    if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
    if (!["GET", "HEAD"].includes(method) && this.csrf) init.headers["X-CSRF-Token"] = this.csrf;
    const response = await fetch(`${this.base}${path}`, init);
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401 && allow401) return null;
    if (!response.ok) {
      const error = new Error(payload?.error?.message || "请求失败，请稍后重试。");
      error.code = payload?.error?.code || "REQUEST_FAILED";
      error.status = response.status;
      throw error;
    }
    if (payload?.csrf) this.csrf = payload.csrf;
    return payload;
  }
}
