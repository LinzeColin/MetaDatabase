import assert from "node:assert/strict";
import test from "node:test";
import { formatVisitorTime } from "../app/_components/workbench/visitor-time.ts";

test("visitor time uses the visitor's local date, clock, weekday, and greeting", () => {
  const morning = formatVisitorTime(new Date(2026, 7, 11, 8, 3));
  const afternoon = formatVisitorTime(new Date(2026, 7, 11, 17, 8));

  assert.deepEqual(morning, {
    date: "2026年8月11日",
    greeting: "早上好，小张张～",
    time: "08:03",
    weekday: "星期二",
  });
  assert.equal(afternoon.date, "2026年8月11日");
  assert.equal(afternoon.time, "17:08");
  assert.equal(afternoon.weekday, "星期二");
  assert.equal(afternoon.greeting, "下午好，小张张～");
});
