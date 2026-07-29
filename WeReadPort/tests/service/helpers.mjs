import { loadConfig } from "../../service/platform/config.mjs";
import { PlatformStore } from "../../service/platform/store.mjs";
import { MemoryObjectStore } from "../../service/platform/object-store.mjs";
import { PlatformService } from "../../service/platform/service.mjs";

export function testConfig(overrides = {}) {
  const secret = Buffer.alloc(32, 19).toString("base64");
  const base = loadConfig({
    NODE_ENV: "test",
    WRP_PUBLIC_BASE_URL: "https://weread.linzezhang.com",
    WRP_SESSION_PEPPER: secret,
    WRP_CREDENTIAL_PEPPER: Buffer.alloc(32, 23).toString("base64"),
    WRP_KEYRING_JSON: JSON.stringify({ test: Buffer.alloc(32, 29).toString("base64") }),
    WRP_ACTIVE_KEY_ID: "test",
    WRP_INTERNAL_PROXY_SECRET: "test-internal-proxy-secret-not-for-production",
    WRP_OBJECT_STORE_MODE: "memory",
    WRP_GOOGLE_CLIENT_ID: "google-client",
    WRP_GOOGLE_CLIENT_SECRET: "google-secret",
    WRP_GITHUB_CLIENT_ID: "github-client",
    WRP_GITHUB_CLIENT_SECRET: "github-secret",
    WRP_NOTION_CLIENT_ID: "notion-client",
    WRP_NOTION_CLIENT_SECRET: "notion-secret",
  }, { test: true });
  return Object.freeze({ ...base, ...overrides, providers: Object.freeze({ ...base.providers, ...(overrides.providers || {}) }) });
}

export function testPlatform({ fetchImpl = async () => new Response('{"errcode":0}', { status: 200, headers: { "Content-Type": "application/json" } }), clock = () => Date.now(), config = testConfig() } = {}) {
  const store = new PlatformStore(":memory:", { clock });
  const objectStore = new MemoryObjectStore();
  const service = new PlatformService({ store, objectStore, config, fetchImpl, clock });
  return { store, objectStore, service, config, close: () => store.close() };
}

export function requestContext() {
  return { userAgent: "node-test", ipPrefix: "203.0.113.0/24" };
}
