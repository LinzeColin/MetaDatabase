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
  bindWeRead(key) { return this.request("/auth/link/weread", { method: "POST", body: { key } }); }
  rotateWeRead(key) { return this.request("/auth/rotate/weread", { method: "POST", body: { key } }); }
  reauthPassword(password) { return this.request("/auth/reauth/password", { method: "POST", body: { password } }); }
  reauthWeRead(key) { return this.request("/auth/reauth/weread", { method: "POST", body: { key } }); }
  configurePassword(input) { return this.request("/account/password", { method: "POST", body: input }); }
  sessions() { return this.request("/account/sessions"); }
  revokeSession(id) { return this.request(`/account/sessions/${encodeURIComponent(id)}`, { method: "DELETE", body: {} }); }
  revokeOtherSessions() { return this.request("/account/sessions/revoke-others", { method: "POST", body: {} }); }
  notes() { return this.request("/notes?limit=500"); }
  note(id) { return this.request(`/notes/${encodeURIComponent(id)}`); }
  saveNote(note) { return this.request("/notes", { method: "POST", body: note }); }
  deleteNote(id, expectedVersion) { return this.request(`/notes/${encodeURIComponent(id)}?expectedVersion=${encodeURIComponent(expectedVersion)}`, { method: "DELETE", body: {} }); }
  syncPull(cursor = 0) { return this.request("/sync/pull", { method: "POST", body: { cursor, limit: 500 } }); }
  syncPush(operations) { return this.request("/sync/push", { method: "POST", body: { operations } }); }
  wereadSync(mode = "auto") { return this.request("/weread/sync", { method: "POST", body: { mode, recommendationPages: 3 } }); }
  providerItems(provider, params = {}) { const query = new URLSearchParams(params); return this.request(`/imports/${provider}/items?${query}`); }
  startImport(provider, selection) { return this.request(`/imports/${provider}/start`, { method: "POST", body: { selection }, headers: { "Idempotency-Key": crypto.randomUUID() } }); }
  importJob(id) { return this.request(`/imports/jobs/${encodeURIComponent(id)}`); }
  analytics() { return this.request("/analytics/dashboard"); }
  exportWeRead() { return this.request("/weread/export"); }
  exportAccount() { return this.request("/account/export"); }
  deleteAccount() { return this.request("/account/delete", { method: "POST", body: {} }); }
  businessLines() { return this.request("/status/business-lines"); }

  async request(path, { method = "GET", body, headers = {}, allow401 = false } = {}) {
    const init = { method, credentials: "include", headers: { Accept: "application/json", ...headers } };
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
