import assert from "node:assert/strict";
import test from "node:test";

import { requestWithTimeout } from "../app/_components/workbench/request-timeout.ts";

test("workbench request timeout aborts a stalled first-party request", async () => {
  const originalFetch = globalThis.fetch;
  let observedAbort = false;

  globalThis.fetch = ((_: string, init?: RequestInit) => new Promise<Response>((_, reject) => {
    init?.signal?.addEventListener("abort", () => {
      observedAbort = true;
      reject(new DOMException("Request aborted", "AbortError"));
    }, { once: true });
  })) as typeof fetch;

  try {
    await assert.rejects(
      () => requestWithTimeout("/api/mydairy/ledger", { credentials: "same-origin" }, 20),
      { name: "AbortError" },
    );
    assert.equal(observedAbort, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("workbench request timeout clears its timer after a successful response", async () => {
  const originalFetch = globalThis.fetch;
  let signal: AbortSignal | undefined;

  globalThis.fetch = ((_: string, init?: RequestInit) => {
    signal = init?.signal ?? undefined;
    return Promise.resolve(new Response(null, { status: 204 }));
  }) as typeof fetch;

  try {
    const response = await requestWithTimeout("/api/mydairy/ledger", { credentials: "same-origin" }, 20);
    assert.equal(response.status, 204);
    await new Promise((resolve) => setTimeout(resolve, 30));
    assert.equal(signal?.aborted, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
