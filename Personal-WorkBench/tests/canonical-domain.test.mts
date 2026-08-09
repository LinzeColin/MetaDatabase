import assert from "node:assert/strict";
import test from "node:test";
import {
  CANONICAL_WORKBENCH_ORIGIN,
  canonicalLegacyUrl,
  isLegacyPlatformHost,
} from "../app/_components/workbench/canonical-domain.ts";

test("legacy browser URLs preserve the active page query on the canonical domain", () => {
  assert.equal(
    canonicalLegacyUrl("https://huchuliang-workbench.linzezhang35.chatgpt.site/?view=period"),
    `${CANONICAL_WORKBENCH_ORIGIN}/?view=period`,
  );
  assert.equal(
    canonicalLegacyUrl("https://huchuliang-workbench.linzezhang35.chatgpt.site/?reference=home"),
    `${CANONICAL_WORKBENCH_ORIGIN}/?reference=home`,
  );
  assert.equal(canonicalLegacyUrl("https://mydairy.linzezhang.com/?view=period"), null);
});

test("only the immutable legacy Sites host is normalized", () => {
  assert.equal(isLegacyPlatformHost("huchuliang-workbench.linzezhang35.chatgpt.site"), true);
  assert.equal(isLegacyPlatformHost("mydairy.linzezhang.com"), false);
  assert.equal(isLegacyPlatformHost(null), false);
});
