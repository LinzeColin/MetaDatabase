import assert from "node:assert/strict";
import test from "node:test";
import {
  CANONICAL_WORKBENCH_ORIGIN,
  canonicalWorkbenchUrl,
  isLegacyPlatformHost,
} from "../server/http/canonical-workbench-url.ts";

test("canonical workbench URL preserves the active page query", () => {
  assert.equal(
    canonicalWorkbenchUrl({ view: "period" }),
    `${CANONICAL_WORKBENCH_ORIGIN}/?view=period`,
  );
  assert.equal(
    canonicalWorkbenchUrl({ reference: "home" }),
    `${CANONICAL_WORKBENCH_ORIGIN}/?reference=home`,
  );
});

test("only the immutable legacy Sites host is normalized", () => {
  assert.equal(isLegacyPlatformHost("huchuliang-workbench.linzezhang35.chatgpt.site"), true);
  assert.equal(isLegacyPlatformHost("mydairy.linzezhang.com"), false);
  assert.equal(isLegacyPlatformHost(null), false);
});
