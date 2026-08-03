import { rejectClientTenantFields } from "@/server/security/tenant";

type FieldKind = "string" | "integer" | "date" | "boolean" | "enum";

type FieldRule = {
  column: string;
  kind: FieldKind;
  required?: boolean;
  nullable?: boolean;
  min?: number;
  max?: number;
  values?: readonly string[];
  defaultValue?: string | number | boolean | null;
  serverNow?: boolean;
  nonZero?: boolean;
};

export type TenantResource = {
  table: string;
  orderBy: string;
  fields: Record<string, FieldRule>;
};

const string = (column: string, min: number, max: number, required = true): FieldRule => ({
  column,
  kind: "string",
  min,
  max,
  required,
});
const integer = (column: string, min: number, max: number, required = true): FieldRule => ({
  column,
  kind: "integer",
  min,
  max,
  required,
});
const date = (column: string, required = true): FieldRule => ({ column, kind: "date", required });
const boolean = (column: string, defaultValue?: boolean): FieldRule => ({
  column,
  kind: "boolean",
  required: false,
  defaultValue,
});
const choice = (
  column: string,
  values: readonly string[],
  required = true,
  defaultValue?: string,
): FieldRule => ({ column, kind: "enum", values, required, defaultValue });
const optionalText = (column: string, max: number): FieldRule => ({
  column,
  kind: "string",
  min: 0,
  max,
  required: false,
  defaultValue: "",
});
const optionalDate = (column: string): FieldRule => ({
  column,
  kind: "date",
  required: false,
  nullable: true,
  defaultValue: null,
});
const optionalInteger = (column: string, min: number, max: number): FieldRule => ({
  column,
  kind: "integer",
  min,
  max,
  required: false,
  nullable: true,
  defaultValue: null,
});
const optionalId = (column: string): FieldRule => ({
  column,
  kind: "string",
  min: 1,
  max: 160,
  required: false,
  nullable: true,
  defaultValue: null,
});
const serverNow = (column: string): FieldRule => ({
  column,
  kind: "integer",
  min: 0,
  max: 9_999_999_999_999,
  required: false,
  serverNow: true,
});

/**
 * Every identifier is a static whitelist entry. Request path values are never
 * interpolated into SQL unless they first resolve through this map.
 */
export const tenantResources = {
  habits: {
    table: "habit_definitions",
    orderBy: "sort_order ASC, updated_at DESC",
    fields: {
      title: string("title", 1, 80),
      iconKey: string("icon_key", 1, 80),
      sortOrder: integer("sort_order", -100000, 100000, false),
      active: boolean("active", true),
    },
  },
  "habit-checkins": {
    table: "habit_checkins",
    orderBy: "local_date DESC, updated_at DESC",
    fields: {
      habitId: string("habit_id", 1, 160),
      localDate: date("local_date"),
      checkedAt: serverNow("checked_at"),
    },
  },
  todos: {
    table: "todos",
    orderBy: "completed ASC, due_date ASC, updated_at DESC",
    fields: {
      title: string("title", 1, 300),
      note: optionalText("note", 5000),
      dueDate: optionalDate("due_date"),
      priority: choice("priority", ["low", "normal", "high"], false, "normal"),
      completed: boolean("completed", false),
      completedAt: optionalInteger("completed_at", 0, 9_999_999_999_999),
    },
  },
  ledger: {
    table: "ledger_entries",
    orderBy: "local_date DESC, updated_at DESC",
    fields: {
      kind: choice("kind", ["expense", "income"]),
      amountCents: integer("amount_cents", 1, 9_999_999_999),
      currency: choice("currency", ["CNY"], false, "CNY"),
      localDate: date("local_date"),
      category: string("category", 1, 40),
      note: optionalText("note", 1000),
    },
  },
  food: {
    table: "food_entries",
    orderBy: "local_date DESC, updated_at DESC",
    fields: {
      foodName: string("food_name", 1, 200),
      calories: integer("calories", 0, 20000),
      meal: choice("meal", ["breakfast", "lunch", "dinner", "snack"]),
      localDate: date("local_date"),
      note: optionalText("note", 2000),
      photoObjectId: optionalId("photo_object_id"),
      source: string("source", 1, 80, false),
    },
  },
  exercise: {
    table: "exercise_entries",
    orderBy: "local_date DESC, updated_at DESC",
    fields: {
      activity: string("activity", 1, 120),
      durationMinutes: integer("duration_minutes", 1, 1440),
      caloriesBurned: optionalInteger("calories_burned", 0, 20000),
      localDate: date("local_date"),
      note: optionalText("note", 2000),
    },
  },
  weights: {
    table: "weight_entries",
    orderBy: "local_date DESC, updated_at DESC",
    fields: {
      weightGrams: integer("weight_grams", 10000, 500000),
      localDate: date("local_date"),
      note: optionalText("note", 1000),
    },
  },
  schedule: {
    table: "schedule_events",
    orderBy: "starts_at ASC, updated_at DESC",
    fields: {
      title: string("title", 1, 200),
      note: optionalText("note", 5000),
      startsAt: integer("starts_at", 0, 9_999_999_999_999),
      endsAt: optionalInteger("ends_at", 0, 9_999_999_999_999),
      allDay: boolean("all_day", false),
    },
  },
  anniversaries: {
    table: "anniversaries",
    orderBy: "local_date ASC, updated_at DESC",
    fields: {
      title: string("title", 1, 160),
      localDate: date("local_date"),
      repeatYearly: boolean("repeat_yearly", true),
      note: optionalText("note", 2000),
    },
  },
  diary: {
    table: "diary_entries",
    orderBy: "local_date DESC, updated_at DESC",
    fields: {
      localDate: date("local_date"),
      mood: optionalText("mood", 80),
      title: optionalText("title", 200),
      body: string("body", 1, 30000),
      photoObjectId: optionalId("photo_object_id"),
    },
  },
  "savings-goals": {
    table: "savings_goals",
    orderBy: "archived ASC, updated_at DESC",
    fields: {
      title: string("title", 1, 160),
      targetCents: integer("target_cents", 1, 9_999_999_999),
      currency: choice("currency", ["CNY"], false, "CNY"),
      targetDate: optionalDate("target_date"),
      archived: boolean("archived", false),
    },
  },
  "savings-transactions": {
    table: "savings_transactions",
    orderBy: "local_date DESC, updated_at DESC",
    fields: {
      goalId: string("goal_id", 1, 160),
      amountCents: { ...integer("amount_cents", -9_999_999_999, 9_999_999_999), nonZero: true },
      localDate: date("local_date"),
      note: optionalText("note", 1000),
    },
  },
  periods: {
    table: "period_entries",
    orderBy: "start_date DESC, updated_at DESC",
    fields: {
      startDate: date("start_date"),
      endDate: date("end_date"),
      note: optionalText("note", 2000),
    },
  },
} satisfies Record<string, TenantResource>;

export type TenantResourceName = keyof typeof tenantResources;

export class ResourceInputError extends Error {
  status = 400;
  code = "INVALID_INPUT";

  constructor() {
    super("The request data is invalid.");
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeDate(value: unknown): string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw new ResourceInputError();
  }
  return value;
}

function normalizeValue(rule: FieldRule, value: unknown): string | number | boolean | null {
  if (value === null && rule.nullable) return null;

  if (rule.kind === "string") {
    if (typeof value !== "string") throw new ResourceInputError();
    const normalized = value.trim();
    if (normalized.length < (rule.min ?? 0) || normalized.length > (rule.max ?? Number.MAX_SAFE_INTEGER)) {
      throw new ResourceInputError();
    }
    return normalized;
  }
  if (rule.kind === "integer") {
    if (typeof value !== "number" || !Number.isSafeInteger(value)) throw new ResourceInputError();
    if (value < (rule.min ?? Number.MIN_SAFE_INTEGER) || value > (rule.max ?? Number.MAX_SAFE_INTEGER)) {
      throw new ResourceInputError();
    }
    if (rule.nonZero && value === 0) throw new ResourceInputError();
    return value;
  }
  if (rule.kind === "boolean") {
    if (typeof value !== "boolean") throw new ResourceInputError();
    return value;
  }
  if (rule.kind === "date") return normalizeDate(value);
  if (typeof value !== "string" || !rule.values?.includes(value)) throw new ResourceInputError();
  return value;
}

export function getTenantResource(value: string): TenantResource | null {
  return Object.hasOwn(tenantResources, value)
    ? tenantResources[value as TenantResourceName]
    : null;
}

export function normalizeResourceInput(
  resource: TenantResource,
  input: unknown,
  mode: "create" | "update",
): Record<string, string | number | boolean | null> {
  rejectClientTenantFields(input);
  if (!isPlainObject(input)) throw new ResourceInputError();

  const allowed = new Set(Object.keys(resource.fields));
  if (Object.keys(input).some((key) => !allowed.has(key))) throw new ResourceInputError();

  const result: Record<string, string | number | boolean | null> = {};
  for (const [field, rule] of Object.entries(resource.fields)) {
    const hasValue = Object.hasOwn(input, field);
    if (!hasValue) {
      if (mode === "create" && rule.required) throw new ResourceInputError();
      if (mode === "create" && rule.serverNow) result[rule.column] = Date.now();
      if (mode === "create" && Object.hasOwn(rule, "defaultValue")) result[rule.column] = rule.defaultValue ?? null;
      continue;
    }
    result[rule.column] = normalizeValue(rule, input[field]);
  }

  if (mode === "update" && Object.keys(result).length === 0) throw new ResourceInputError();
  return result;
}
