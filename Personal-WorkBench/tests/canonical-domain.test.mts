import assert from "node:assert/strict";
import test from "node:test";
import {
  CANONICAL_MYDAIRY_ORIGIN,
  canonicalRetiredHostUrl,
  canonicalRetiredUrl,
  isRetiredCompatibilityHost,
} from "../app/_components/workbench/canonical-domain.ts";

test("retired browser URLs preserve the active page query on the canonical domain", () => {
  assert.equal(
    canonicalRetiredUrl("https://huchuliang-workbench.linzezhang35.chatgpt.site/?view=period"),
    `${CANONICAL_MYDAIRY_ORIGIN}/?view=period`,
  );
  assert.equal(
    canonicalRetiredUrl("https://huchuliang-workbench.linzezhang35.chatgpt.site/?reference=home"),
    `${CANONICAL_MYDAIRY_ORIGIN}/?reference=home`,
  );
  assert.equal(canonicalRetiredUrl("https://mydairy.linzezhang.com/?view=period"), null);
});

test("only the retired Sites host is normalized", () => {
  assert.equal(isRetiredCompatibilityHost("huchuliang-workbench.linzezhang35.chatgpt.site"), true);
  assert.equal(isRetiredCompatibilityHost("huchuliang-workbench.linzezhang35.chatgpt.site:443"), true);
  assert.equal(isRetiredCompatibilityHost("mydairy.linzezhang.com"), false);
  assert.equal(isRetiredCompatibilityHost(null), false);
});

test("server-side host normalization preserves incoming query parameters", () => {
  assert.equal(
    canonicalRetiredHostUrl("huchuliang-workbench.linzezhang35.chatgpt.site", "view=period&tag=one&tag=two"),
    `${CANONICAL_MYDAIRY_ORIGIN}/?view=period&tag=one&tag=two`,
  );
  assert.equal(canonicalRetiredHostUrl("mydairy.linzezhang.com", "view=period"), null);
});
