import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

const migrationFiles = ["drizzle/0001_auth_and_product.sql", "drizzle/0002_s2_tenant_indexes.sql"];

function nowSeconds(days = 0) {
  return Date.now() + days * 86400000;
}

function formatDate(date) {
  const d = date instanceof Date ? date : new Date(date);
  const yy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

async function openDb() {
  const db = new DatabaseSync(":memory:");
  for (const file of migrationFiles) {
    db.exec(await readFile(file, "utf8"));
  }
  const t = Date.now();
  db
    .prepare(`INSERT INTO "user" (id, name, email, emailVerified, createdAt, updatedAt)
      VALUES (?, ?, ?, 1, ?, ?)`)
    .run("user_a", "A", "a@example.test", t, t);
  db
    .prepare(`INSERT INTO "user" (id, name, email, emailVerified, createdAt, updatedAt)
      VALUES (?, ?, ?, 1, ?, ?)`)
    .run("user_b", "B", "b@example.test", t, t);
  return db;
}

function insert(db, table, id, userId, values) {
  const now = Date.now();
  const columns = ["id", "user_id", ...Object.keys(values), "created_at", "updated_at"];
  const placeholders = columns.map(() => "?").join(", ");
  const binds = [id, userId, ...Object.values(values).map((value) => value), now, now];
  db
    .prepare(`INSERT INTO "${table}"(${columns.map((name) => `"${name}"`).join(", ")}) VALUES (${placeholders})`)
    .run(...binds);
}

function update(db, table, id, userId, values) {
  const now = Date.now();
  const assignments = [...Object.keys(values).map((name) => `"${name}" = ?`), '"updated_at" = ?'];
  const sql = `UPDATE "${table}" SET ${assignments.join(", ")} WHERE id = ? AND user_id = ?`;
  db.prepare(sql).run(...Object.values(values), now, id, userId);
}

function select(db, table, id, userId) {
  return db.prepare(`SELECT * FROM "${table}" WHERE id = ? AND user_id = ? LIMIT 1`).get(id, userId);
}

function countByUser(db, table, userId) {
  return db.prepare(`SELECT COUNT(*) AS count FROM "${table}" WHERE user_id = ?`).get(userId).count;
}

test("module matrix: each module supports basic tenant CRUD in local D1 contract", async () => {
  const db = await openDb();
  try {
    // 1) habits
    insert(db, "habit_definitions", "habit-01", "user_a", {
      title: "早起",
      icon_key: "habit_early.png",
      sort_order: 1,
      active: 1,
    });
    assert.equal(countByUser(db, "habit_definitions", "user_a"), 1);
    assert.equal(select(db, "habit_definitions", "habit-01", "user_a")?.title, "早起");
    update(db, "habit_definitions", "habit-01", "user_a", { title: "早起(完成)" });
    assert.equal(select(db, "habit_definitions", "habit-01", "user_a")?.title, "早起(完成)");

    // 2) habit checkins (FK depends on habit)
    insert(db, "habit_checkins", "check-01", "user_a", {
      habit_id: "habit-01",
      local_date: formatDate(new Date()),
      checked_at: Date.now(),
    });
    assert.equal(select(db, "habit_checkins", "check-01", "user_a")?.habit_id, "habit-01");

    // 3) todos
    insert(db, "todos", "todo-01", "user_a", {
      title: "喝水",
      note: "今天要多喝水",
      due_date: formatDate(new Date()),
      priority: "normal",
      completed: 0,
      completed_at: null,
    });
    assert.equal(select(db, "todos", "todo-01", "user_a")?.title, "喝水");

    // 4) ledger
    insert(db, "ledger_entries", "ledger-01", "user_a", {
      kind: "expense",
      amount_cents: 1200,
      currency: "CNY",
      local_date: formatDate(new Date()),
      category: "饮食",
      note: "午餐",
    });
    assert.equal(select(db, "ledger_entries", "ledger-01", "user_a")?.kind, "expense");

    // 5) food
    insert(db, "food_entries", "food-01", "user_a", {
      food_name: "鸡蛋",
      calories: 155,
      meal: "breakfast",
      local_date: formatDate(new Date()),
      note: "加餐",
      photo_object_id: null,
      source: "manual",
    });
    assert.equal(select(db, "food_entries", "food-01", "user_a")?.food_name, "鸡蛋");

    // 6) exercise
    insert(db, "exercise_entries", "exercise-01", "user_a", {
      activity: "慢跑",
      duration_minutes: 30,
      calories_burned: null,
      local_date: formatDate(new Date()),
      note: "晚餐后",
    });
    assert.equal(select(db, "exercise_entries", "exercise-01", "user_a")?.activity, "慢跑");

    // 7) weights
    insert(db, "weight_entries", "weight-01", "user_a", {
      weight_grams: 58000,
      local_date: formatDate(new Date()),
      note: "基础记录",
    });
    assert.equal(select(db, "weight_entries", "weight-01", "user_a")?.weight_grams, 58000);

    // 8) schedule
    const start = Math.floor(nowSeconds() / 1000);
    insert(db, "schedule_events", "schedule-01", "user_a", {
      title: "每周总结",
      note: "周日回顾",
      starts_at: start,
      ends_at: null,
      all_day: 1,
    });
    assert.equal(select(db, "schedule_events", "schedule-01", "user_a")?.title, "每周总结");

    // 9) anniversaries
    insert(db, "anniversaries", "anniversary-01", "user_a", {
      title: "纪念日",
      local_date: "2026-08-20",
      repeat_yearly: 1,
      note: "每年关注",
    });
    assert.equal(select(db, "anniversaries", "anniversary-01", "user_a")?.title, "纪念日");

    // 10) diary
    insert(db, "diary_entries", "diary-01", "user_a", {
      local_date: formatDate(new Date()),
      mood: "平静",
      title: "日记标题",
      body: "今天是平静的一天，记录一下。",
      photo_object_id: null,
    });
    assert.equal(select(db, "diary_entries", "diary-01", "user_a")?.title, "日记标题");

    // 11) savings goals + transactions
    insert(db, "savings_goals", "goal-01", "user_a", {
      title: "应急金",
      target_cents: 300000,
      currency: "CNY",
      target_date: formatDate(new Date(Date.now() + 180 * 86400000)),
      archived: 0,
    });
    insert(db, "savings_transactions", "savings-tx-01", "user_a", {
      goal_id: "goal-01",
      amount_cents: 50000,
      local_date: formatDate(new Date()),
      note: "每月储蓄",
    });
    assert.equal(select(db, "savings_transactions", "savings-tx-01", "user_a")?.goal_id, "goal-01");

    // 12) periods
    insert(db, "period_entries", "period-01", "user_a", {
      start_date: "2026-08-01",
      end_date: "2026-08-05",
      note: "例行记录",
    });
    assert.equal(select(db, "period_entries", "period-01", "user_a")?.note, "例行记录");

    // Cross-tenant isolation sanity for each table
    const moduleRows = [
      "habit_definitions",
      "habit_checkins",
      "todos",
      "ledger_entries",
      "food_entries",
      "exercise_entries",
      "weight_entries",
      "schedule_events",
      "anniversaries",
      "diary_entries",
      "savings_goals",
      "savings_transactions",
      "period_entries",
    ];
    for (const table of moduleRows) {
      const rowCountOwn = countByUser(db, table, "user_a");
      const rowCountOther = countByUser(db, table, "user_b");
      assert.equal(rowCountOwn > 0, true, `${table}: missing tenant data`);
      assert.equal(rowCountOther, 0, `${table}: leaked tenant data`);
    }

    // Delete and confirm idempotent re-create path
    db.prepare('DELETE FROM "todos" WHERE id = ? AND user_id = ?').run("todo-01", "user_a");
    assert.equal(select(db, "todos", "todo-01", "user_a"), undefined);
    update(db, "ledger_entries", "ledger-01", "user_a", { note: "午餐(更新)" });
    assert.equal(select(db, "ledger_entries", "ledger-01", "user_a")?.note, "午餐(更新)");
  } finally {
    db.close();
  }
});
