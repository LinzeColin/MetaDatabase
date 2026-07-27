import { sanitizeText } from "./crypto.mjs";
import { fetchWithPolicy } from "./network.mjs";

const DEFINITIONS = Object.freeze({
  google: Object.freeze({
    label: "Google",
    authorizationUrl: "https://accounts.google.com/o/oauth2/v2/auth",
    tokenUrl: "https://oauth2.googleapis.com/token",
    loginScopes: ["openid", "email", "profile"],
    importScopes: ["https://www.googleapis.com/auth/drive.readonly"],
    pkce: true,
  }),
  github: Object.freeze({
    label: "GitHub",
    authorizationUrl: "https://github.com/login/oauth/authorize",
    tokenUrl: "https://github.com/login/oauth/access_token",
    loginScopes: [],
    importScopes: [],
    pkce: true,
    implementation: "github-app-user-token",
  }),
  notion: Object.freeze({
    label: "Notion",
    authorizationUrl: "https://api.notion.com/v1/oauth/authorize",
    tokenUrl: "https://api.notion.com/v1/oauth/token",
    loginScopes: [],
    importScopes: [],
    pkce: false,
  }),
});

export function providerDefinition(provider) {
  const definition = DEFINITIONS[String(provider)];
  if (!definition) throw new Error("不支持的登录或导入平台。");
  return definition;
}

export function connectionSupportsImport(provider, scopes = "") {
  const definition = providerDefinition(provider);
  if (["notion", "github"].includes(provider)) return true;
  const granted = new Set(String(scopes || "").split(/[\s,]+/).filter(Boolean));
  return definition.importScopes.every(scope => granted.has(scope));
}

export function buildAuthorizationUrl(provider, { clientId, redirectUri, state, challenge, intent }) {
  const definition = providerDefinition(provider);
  if (!clientId) throw new Error(`${definition.label} 登录尚未配置。`);
  const url = new URL(definition.authorizationUrl);
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("state", state);
  if (provider === "notion") {
    url.searchParams.set("owner", "user");
  } else {
    const scopes = [...definition.loginScopes, ...(intent === "import" ? definition.importScopes : [])];
    if (scopes.length) url.searchParams.set("scope", scopes.join(" "));
    if (provider === "google") {
      url.searchParams.set("access_type", "offline");
      url.searchParams.set("include_granted_scopes", "true");
      url.searchParams.set("prompt", intent === "login" ? "select_account" : "consent");
    }
  }
  if (definition.pkce) {
    url.searchParams.set("code_challenge", challenge);
    url.searchParams.set("code_challenge_method", "S256");
  }
  return url.toString();
}

export async function exchangeAuthorizationCode(provider, { code, verifier, redirectUri, config, fetchImpl = fetch }) {
  const definition = providerDefinition(provider);
  const credentials = config.providers[provider];
  if (!credentials?.clientId || !credentials?.clientSecret) throw new Error(`${definition.label} OAuth 尚未配置。`);
  const policy = networkPolicy(config, { attempts: 1, retry: false });
  let response;
  if (provider === "notion") {
    response = await fetchWithPolicy(fetchImpl, definition.tokenUrl, {
      method: "POST",
      redirect: "manual",
      headers: {
        Authorization: `Basic ${Buffer.from(`${credentials.clientId}:${credentials.clientSecret}`).toString("base64")}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ grant_type: "authorization_code", code, redirect_uri: redirectUri }),
    }, policy);
  } else {
    const body = new URLSearchParams({ client_id: credentials.clientId, client_secret: credentials.clientSecret, code, redirect_uri: redirectUri });
    if (verifier) body.set("code_verifier", verifier);
    response = await fetchWithPolicy(fetchImpl, definition.tokenUrl, {
      method: "POST",
      redirect: "manual",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body,
    }, policy);
  }
  rejectRedirect(response, definition.label);
  const payload = await boundedJson(response, 2 * 1024 * 1024);
  if (!response.ok || payload.error) throw new Error(`${definition.label} 授权失败。`);
  const accessToken = String(payload.access_token || "");
  if (!accessToken) throw new Error(`${definition.label} 未返回访问令牌。`);
  const identity = provider === "notion" ? notionIdentity(payload) : await fetchProviderIdentity(provider, accessToken, fetchImpl, networkPolicy(config));
  return {
    accessToken,
    refreshToken: payload.refresh_token ? String(payload.refresh_token) : null,
    expiresIn: Number(payload.expires_in || 0) || null,
    scopes: String(payload.scope || ""),
    tokenType: String(payload.token_type || "Bearer"),
    identity,
    rawMetadata: provider === "notion"
      ? { workspaceId: payload.workspace_id, workspaceName: payload.workspace_name }
      : provider === "github" ? { credentialType: "github_app_user_token" } : {},
  };
}

export async function fetchProviderIdentity(provider, accessToken, fetchImpl = fetch, policy = {}) {
  if (provider === "google") {
    const payload = await authorizedJson(fetchImpl, "https://openidconnect.googleapis.com/v1/userinfo", accessToken, {}, {}, policy);
    return { subject: String(payload.sub), email: payload.email ? String(payload.email).toLowerCase() : null, displayName: sanitizeText(payload.name || payload.email || "Google 用户", 120), avatarUrl: payload.picture || null };
  }
  if (provider === "github") {
    const headers = { "X-GitHub-Api-Version": "2022-11-28" };
    const user = await authorizedJson(fetchImpl, "https://api.github.com/user", accessToken, headers, {}, policy);
    let email = user.email ? String(user.email).toLowerCase() : null;
    if (!email) {
      const emails = await authorizedJson(fetchImpl, "https://api.github.com/user/emails", accessToken, headers, {}, policy);
      const primary = Array.isArray(emails) ? emails.find(item => item.primary && item.verified) : null;
      email = primary?.email ? String(primary.email).toLowerCase() : null;
    }
    return { subject: String(user.id), email, displayName: sanitizeText(user.name || user.login || "GitHub 用户", 120), avatarUrl: user.avatar_url || null, login: user.login || null };
  }
  throw new Error("无法读取平台用户身份。");
}

export async function listProviderItems(provider, accessToken, { container = "", cursor = "", fetchImpl = fetch, limit = 200, networkPolicy: policy = {} } = {}) {
  if (provider === "google") return listGoogle(accessToken, { cursor, fetchImpl, limit, policy });
  if (provider === "notion") return listNotion(accessToken, { cursor, fetchImpl, limit, policy });
  if (provider === "github") return listGitHub(accessToken, { container, cursor, fetchImpl, limit, policy });
  throw new Error("此平台不支持云端导入列表。");
}

export async function fetchProviderDocuments(provider, accessToken, selection, { fetchImpl = fetch, maxBytes = 50 * 1024 * 1024, networkPolicy: policy = {} } = {}) {
  const items = Array.isArray(selection?.items) ? selection.items : [];
  const documents = [];
  let totalBytes = 0;
  for (const item of items) {
    let document;
    if (provider === "google") document = await fetchGoogleDocument(accessToken, item, fetchImpl, policy);
    else if (provider === "notion") document = await fetchNotionDocument(accessToken, item, fetchImpl, policy);
    else if (provider === "github") document = await fetchGitHubDocument(accessToken, item, fetchImpl, policy);
    else throw new Error("不支持的云端导入平台。");
    totalBytes += Buffer.byteLength(document.content, "utf8");
    if (totalBytes > maxBytes) throw new Error("所选内容超过本次导入上限，请减少选择后重试。");
    documents.push(document);
  }
  return documents;
}

async function listGoogle(token, { cursor, fetchImpl, limit, policy }) {
  const url = new URL("https://www.googleapis.com/drive/v3/files");
  url.searchParams.set("pageSize", String(Math.min(limit, 100)));
  url.searchParams.set("q", "trashed = false");
  url.searchParams.set("orderBy", "modifiedTime desc");
  url.searchParams.set("fields", "nextPageToken,files(id,name,mimeType,modifiedTime,size,webViewLink,parents)");
  if (cursor) url.searchParams.set("pageToken", cursor);
  const payload = await authorizedJson(fetchImpl, url, token, {}, {}, policy);
  const allowed = new Set(["application/vnd.google-apps.document", "text/plain", "text/markdown", "application/json"]);
  return {
    kind: "documents",
    items: (payload.files || []).filter(file => allowed.has(file.mimeType)).map(file => ({ id: file.id, label: sanitizeText(file.name, 180), detail: file.mimeType === "application/vnd.google-apps.document" ? "Google 文档" : file.mimeType, modifiedAt: file.modifiedTime, size: Number(file.size || 0), mimeType: file.mimeType })),
    nextCursor: payload.nextPageToken || null,
  };
}

async function listNotion(token, { cursor, fetchImpl, limit, policy }) {
  const payload = await authorizedJson(fetchImpl, "https://api.notion.com/v1/search", token, { "Notion-Version": "2022-06-28", "Content-Type": "application/json" }, {
    method: "POST",
    body: JSON.stringify({ page_size: Math.min(limit, 100), start_cursor: cursor || undefined, filter: { property: "object", value: "page" }, sort: { direction: "descending", timestamp: "last_edited_time" } }),
  }, { ...policy, retry: true });
  return {
    kind: "documents",
    items: (payload.results || []).map(page => ({ id: page.id, label: notionTitle(page), detail: "Notion 页面", modifiedAt: page.last_edited_time, url: page.url || null })),
    nextCursor: payload.has_more ? payload.next_cursor : null,
  };
}

async function listGitHub(token, { container, cursor, fetchImpl, limit, policy }) {
  const headers = { "X-GitHub-Api-Version": "2022-11-28" };
  if (!container) {
    const installationsUrl = new URL("https://api.github.com/user/installations");
    installationsUrl.searchParams.set("per_page", String(Math.min(limit, 100)));
    if (cursor) installationsUrl.searchParams.set("page", cursor);
    const installations = await authorizedJson(fetchImpl, installationsUrl, token, headers, {}, policy);
    const repositories = [];
    for (const installation of (installations.installations || []).slice(0, 20)) {
      const payload = await authorizedJson(fetchImpl, `https://api.github.com/user/installations/${encodeURIComponent(installation.id)}/repositories?per_page=100`, token, headers, {}, policy);
      for (const repo of payload.repositories || []) repositories.push(repo);
      if (repositories.length >= limit) break;
    }
    return {
      kind: "containers",
      items: repositories.slice(0, limit).map(repo => ({ id: `${repo.full_name}@${repo.default_branch}`, label: repo.full_name, detail: repo.private ? "私有仓库 · GitHub App 只读" : "公开仓库 · GitHub App 只读", modifiedAt: repo.updated_at })),
      nextCursor: installations.total_count > Number(cursor || 1) * Math.min(limit, 100) ? String(Number(cursor || 1) + 1) : null,
      setupHint: repositories.length ? null : "请先在 GitHub 官方页面安装阅迁应用，并只勾选需要导入的仓库。",
    };
  }
  const match = /^([^/]+)\/([^@]+)@(.+)$/.exec(container);
  if (!match) throw new Error("GitHub 仓库标识无效。");
  const [, owner, repo, branch] = match;
  const tree = await authorizedJson(fetchImpl, `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/git/trees/${encodeURIComponent(branch)}?recursive=1`, token, headers, {}, policy);
  if (tree.truncated) throw Object.assign(new Error("仓库文件过多，GitHub 返回的目录不完整。请缩小仓库或导出 ZIP 后使用 Obsidian/本地导入。"), { code: "GITHUB_TREE_TRUNCATED" });
  const allowed = /\.(?:md|markdown|txt|json)$/i;
  return { kind: "documents", container, items: (tree.tree || []).filter(item => item.type === "blob" && allowed.test(item.path)).slice(0, limit).map(item => ({ id: `${container}:${item.path}`, label: item.path, detail: `${Math.ceil(Number(item.size || 0) / 1024)} KB`, size: Number(item.size || 0) })), nextCursor: null, truncated: false };
}

async function fetchGoogleDocument(token, item, fetchImpl, policy) {
  const id = encodeURIComponent(String(item.id));
  const url = item.mimeType === "application/vnd.google-apps.document"
    ? `https://www.googleapis.com/drive/v3/files/${id}/export?mimeType=text/plain`
    : `https://www.googleapis.com/drive/v3/files/${id}?alt=media`;
  const response = await authorizedResponse(fetchImpl, url, token, {}, {}, policy);
  const content = await boundedText(response, 10 * 1024 * 1024);
  return { externalId: String(item.id), title: sanitizeText(item.label || item.name || "Google Drive 文档", 180), content, source: "google", category: "云端导入" };
}

async function fetchNotionDocument(token, item, fetchImpl, policy) {
  const blocks = [];
  await collectNotionBlocks(String(item.id), token, fetchImpl, blocks, 0, policy);
  return { externalId: String(item.id), title: sanitizeText(item.label || "Notion 页面", 180), content: blocks.join("\n\n"), source: "notion", category: "云端导入" };
}

async function collectNotionBlocks(blockId, token, fetchImpl, output, depth, policy) {
  if (depth > 8 || output.length > 1000) return;
  let cursor = "";
  do {
    const url = new URL(`https://api.notion.com/v1/blocks/${encodeURIComponent(blockId)}/children`);
    url.searchParams.set("page_size", "100");
    if (cursor) url.searchParams.set("start_cursor", cursor);
    const payload = await authorizedJson(fetchImpl, url, token, { "Notion-Version": "2022-06-28" }, {}, policy);
    for (const block of payload.results || []) {
      const text = richText(block[block.type]?.rich_text || []);
      if (text) output.push(renderNotionBlock(block.type, text));
      if (block.has_children) await collectNotionBlocks(block.id, token, fetchImpl, output, depth + 1, policy);
    }
    cursor = payload.has_more ? payload.next_cursor : "";
  } while (cursor && output.length <= 1000);
}

async function fetchGitHubDocument(token, item, fetchImpl, policy) {
  const match = /^([^/]+)\/([^@]+)@([^:]+):(.+)$/.exec(String(item.id));
  if (!match) throw new Error("GitHub 文件标识无效。");
  const [, owner, repo, branch, filePath] = match;
  if (!/\.(?:md|markdown|txt|json)$/i.test(filePath) || filePath.split("/").some(part => part === "..")) throw new Error("GitHub 文件类型或路径不允许。");
  const response = await authorizedResponse(fetchImpl, `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/contents/${filePath.split("/").map(encodeURIComponent).join("/")}?ref=${encodeURIComponent(branch)}`, token, { "X-GitHub-Api-Version": "2022-11-28", Accept: "application/vnd.github.raw+json" }, {}, policy);
  const content = await boundedText(response, 10 * 1024 * 1024);
  return { externalId: String(item.id), title: sanitizeText(filePath, 180), content, source: "github", category: "代码仓库导入" };
}

function notionIdentity(payload) {
  const user = payload.owner?.user || {};
  const email = user.person?.email ? String(user.person.email).toLowerCase() : null;
  const subject = `${String(payload.workspace_id || "workspace")}:${String(user.id || "owner")}`;
  return { subject, email, displayName: sanitizeText(user.name || payload.workspace_name || "Notion 用户", 120), avatarUrl: user.avatar_url || null };
}

function notionTitle(page) {
  for (const property of Object.values(page.properties || {})) {
    if (property.type === "title") {
      const value = richText(property.title || []);
      if (value) return sanitizeText(value, 180);
    }
  }
  return "未命名 Notion 页面";
}

function richText(items) { return (items || []).map(item => item.plain_text || item.text?.content || "").join("").trim(); }
function renderNotionBlock(type, text) {
  if (type === "heading_1") return `# ${text}`;
  if (type === "heading_2") return `## ${text}`;
  if (type === "heading_3") return `### ${text}`;
  if (type === "bulleted_list_item") return `- ${text}`;
  if (type === "numbered_list_item") return `1. ${text}`;
  if (type === "to_do") return `- [ ] ${text}`;
  if (type === "quote") return `> ${text}`;
  if (type === "code") return `\`\`\`\n${text}\n\`\`\``;
  return text;
}

async function authorizedJson(fetchImpl, url, token, headers = {}, init = {}, policy = {}) {
  const response = await authorizedResponse(fetchImpl, url, token, headers, init, policy);
  return boundedJson(response, 10 * 1024 * 1024);
}

async function authorizedResponse(fetchImpl, url, token, headers = {}, init = {}, policy = {}) {
  const response = await fetchWithPolicy(fetchImpl, url, { ...init, redirect: "manual", headers: { Authorization: `Bearer ${token}`, Accept: "application/json", ...headers, ...(init.headers || {}) } }, policy);
  rejectRedirect(response, "平台接口");
  if (!response.ok) throw Object.assign(new Error(`平台接口失败：HTTP ${response.status}`), { code: "PROVIDER_UPSTREAM", status: response.status });
  return response;
}

async function boundedJson(response, maxBytes) {
  const text = await boundedText(response, maxBytes);
  try { return JSON.parse(text || "{}"); } catch { throw new Error("平台返回了无效 JSON。"); }
}

async function boundedText(response, maxBytes) {
  const length = Number(response.headers.get("content-length") || 0);
  if (length > maxBytes) throw new Error("平台响应超过安全上限。");
  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes.length > maxBytes) throw new Error("平台响应超过安全上限。");
  return bytes.toString("utf8");
}

export async function refreshProviderAccessToken(provider, refreshToken, { config, fetchImpl = fetch }) {
  const definition = providerDefinition(provider);
  const credentials = config.providers[provider];
  if (!refreshToken || !credentials?.clientId || !credentials?.clientSecret || provider === "notion") throw new Error("此连接无法自动刷新，请重新授权。");
  const body = new URLSearchParams({ client_id: credentials.clientId, client_secret: credentials.clientSecret, grant_type: "refresh_token", refresh_token: refreshToken });
  const response = await fetchWithPolicy(fetchImpl, definition.tokenUrl, { method: "POST", redirect: "manual", headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" }, body }, networkPolicy(config, { attempts: 1, retry: false }));
  rejectRedirect(response, definition.label);
  const payload = await boundedJson(response, 2 * 1024 * 1024);
  if (!response.ok || !payload.access_token) throw new Error(`${definition.label} 连接已失效，请重新授权。`);
  return { accessToken: String(payload.access_token), refreshToken: payload.refresh_token ? String(payload.refresh_token) : refreshToken, expiresIn: Number(payload.expires_in || 0) || null, scopes: String(payload.scope || "") };
}

function networkPolicy(config, overrides = {}) {
  return { timeoutMs: Number(config?.upstreamTimeoutMs || 15_000), attempts: Number(config?.upstreamRetryAttempts || 2), ...overrides };
}
function rejectRedirect(response, label) {
  if (response.status >= 300 && response.status < 400) throw Object.assign(new Error(`${label} 返回了不安全重定向。`), { code: "UPSTREAM_REDIRECT" });
}
