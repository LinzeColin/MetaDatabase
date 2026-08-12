import assert from "node:assert/strict";
import test from "node:test";

import {
  accountReturnPathFromLocation,
  safeAccountReturnPath,
} from "../app/_components/workbench/account-return-path.ts";

test("account consent return keeps only a relative same-origin workbench route", () => {
  assert.equal(safeAccountReturnPath("/?view=ledger"), "/?view=ledger");
  assert.equal(safeAccountReturnPath("/account?from=ledger#privacy"), "/account?from=ledger#privacy");
  assert.equal(safeAccountReturnPath("https://example.test/"), null);
  assert.equal(safeAccountReturnPath("//example.test/"), null);
  assert.equal(safeAccountReturnPath("/\\\\example.test/"), null);
  assert.equal(safeAccountReturnPath("javascript:alert(1)"), null);
  assert.equal(
    accountReturnPathFromLocation({ hash: "", pathname: "/", search: "?view=period" }),
    "/?view=period",
  );
});
