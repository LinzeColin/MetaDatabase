"use client";

/* eslint-disable @next/next/no-img-element */

import { ChangeEvent, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  asBoolean,
  asNumber,
  asText,
  centsToYuan,
  ResourceStatus,
  type ResourceState,
  TenantRecord,
  todayIsoDate,
  useTenantResource,
  withRequestId,
  yuanToCents,
} from "./tenant-resource-client";
import { isDeviceLocalRecord, resolveBrowserRecordScope } from "./local-record-cache";
import { requestWithTimeout } from "./request-timeout";
import { useVisitorTime } from "./visitor-time-client";

const PRIVATE_ASSET_ROOT = "/private-reference-assets";
const RUNTIME_ASSET_ROOT = `${PRIVATE_ASSET_ROOT}/runtime`;

function saveFeedback(saved: TenantRecord, synced: string, local: string): string {
  return isDeviceLocalRecord(saved) ? local : synced;
}

/**
 * Server markup is visible before React attaches mutation handlers. Keep an
 * action inert for only that handoff, then let the resource client serialize
 * the first write while its history read finishes.
 */
function useInteractionReady(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}

type HistoryReadState = Pick<
  ResourceState<TenantRecord>,
  "authRequired" | "consentRequired" | "error" | "loading" | "loginSuggested" | "records"
>;

function canShowEmptyHistory(state: HistoryReadState, reference: boolean): boolean {
  return reference || (
    !state.loading
    && !state.authRequired
    && !state.consentRequired
    && !state.loginSuggested
    && !state.error
    && state.records.length === 0
  );
}

function overviewValue(state: Omit<HistoryReadState, "records">, value: string): string {
  if (state.loading) return "读取中";
  if (state.authRequired || state.loginSuggested) return "未登录";
  if (state.consentRequired) return "未开启";
  if (state.error) return "不确定";
  return value;
}

type HabitCard = {
  icon: string;
  label: string;
};

type LedgerType = "expense" | "income";
type FatlossModule = "exercise" | "weight" | "food";

type HabitDefinition = TenantRecord & {
  icon_key?: string;
  title?: string;
};

type HabitCheckin = TenantRecord & {
  habit_id?: string;
  local_date?: string;
};

type OverviewTodoRecord = TenantRecord & {
  completed?: number | boolean;
};

type LedgerRecord = TenantRecord & {
  amount_cents?: number;
  category?: string;
  kind?: LedgerType;
  local_date?: string;
  note?: string;
};

type FoodRecord = TenantRecord & {
  calories?: number;
  food_name?: string;
  local_date?: string;
  meal?: string;
  note?: string;
  photo_object_id?: string | null;
};

type ExerciseRecord = TenantRecord & {
  activity?: string;
  calories_burned?: number | null;
  duration_minutes?: number;
  local_date?: string;
  note?: string;
};

type WeightRecord = TenantRecord & {
  local_date?: string;
  note?: string;
  weight_grams?: number;
};

type PeriodRecord = TenantRecord & {
  end_date?: string;
  note?: string;
  start_date?: string;
};

type ScheduleRecord = TenantRecord & {
  all_day?: number | boolean;
  ends_at?: number | null;
  note?: string;
  starts_at?: number;
  title?: string;
};

type AnniversaryRecord = TenantRecord & {
  local_date?: string;
  note?: string;
  repeat_yearly?: number | boolean;
  title?: string;
};

type DiaryRecord = TenantRecord & {
  body?: string;
  local_date?: string;
  mood?: string;
  title?: string;
};

type SavingsGoalRecord = TenantRecord & {
  archived?: number | boolean;
  target_cents?: number;
  target_date?: string | null;
  title?: string;
};

type SavingsTransactionRecord = TenantRecord & {
  amount_cents?: number;
  goal_id?: string;
  local_date?: string;
  note?: string;
};

const referenceHomeTime = {
  date: "2026年8月2日",
  greeting: "早上好，小张张～",
  time: "11:27",
  weekday: "星期日",
};

function asset(name: string) {
  return `${RUNTIME_ASSET_ROOT}/${name}`;
}

function inputDate(fixtureDate: string, reference: boolean): string {
  return reference ? fixtureDate : todayIsoDate();
}

function mealApiValue(value: string): "breakfast" | "lunch" | "dinner" | "snack" {
  if (value === "午餐") return "lunch";
  if (value === "晚餐") return "dinner";
  if (value === "加餐") return "snack";
  return "breakfast";
}

function mealLabel(value: unknown): string {
  if (value === "lunch") return "午餐";
  if (value === "dinner") return "晚餐";
  if (value === "snack") return "加餐";
  return "早餐";
}

/**
 * The server deliberately accepts only URL-safe ASCII idempotency tokens.
 * Keep the built-in habit identity stable across reloads without deriving the
 * token from the user-facing (and potentially localized) label.
 */
function builtinHabitIdempotencyKey(index: number): string {
  return `builtin-habit-${String(index + 1).padStart(2, "0")}-v1`;
}

function DeleteRecordButton({
  disabled,
  onDelete,
}: {
  disabled?: boolean;
  onDelete: () => void;
}) {
  return (
    <button className="record-remove" disabled={disabled} onClick={onDelete} type="button">
      删除
    </button>
  );
}

function EditRecordButton({
  disabled,
  onEdit,
}: {
  disabled?: boolean;
  onEdit: () => void;
}) {
  return (
    <button className="record-remove" disabled={disabled} onClick={onEdit} type="button">
      编辑
    </button>
  );
}

export function HomeClient({ habitCards, reference }: { habitCards: HabitCard[]; reference: boolean }) {
  const habits = useTenantResource<HabitDefinition>("habits", { enabled: !reference });
  const checkins = useTenantResource<HabitCheckin>("habit-checkins", { enabled: !reference });
  const todos = useTenantResource<OverviewTodoRecord>("todos", { enabled: !reference });
  const interactionReady = useInteractionReady();
  const overviewLedger = useTenantResource<LedgerRecord>("ledger", { enabled: !reference, sensitive: true });
  const visitorTime = useVisitorTime(reference);
  const [feedback, setFeedback] = useState("");
  const [pendingHabitLabel, setPendingHabitLabel] = useState<string | null>(null);
  const today = useMemo(() => todayIsoDate(), []);

  const completedByHabitId = useMemo(() => {
    const values = new Map<string, HabitCheckin>();
    for (const checkin of checkins.records) {
      const habitId = asText(checkin.habit_id);
      if (habitId && asText(checkin.local_date) === today) values.set(habitId, checkin);
    }
    return values;
  }, [checkins.records, today]);

  const completedLabels = useMemo(() => {
    const labels = new Set<string>();
    for (const habit of habits.records) {
      if (completedByHabitId.has(habit.id)) labels.add(asText(habit.title));
    }
    return labels;
  }, [completedByHabitId, habits.records]);

  const habitTitleById = useMemo(
    () => new Map(habits.records.map((habit) => [habit.id, asText(habit.title, "习惯打卡")])),
    [habits.records],
  );
  const recentCheckins = useMemo(
    () => checkins.records
      .filter((checkin) => Boolean(asText(checkin.habit_id)) && Boolean(asText(checkin.local_date)))
      .sort((left, right) => asText(right.local_date).localeCompare(asText(left.local_date)))
      .slice(0, 10),
    [checkins.records],
  );
  const canShowEmptyCheckinHistory = !checkins.loading
    && !checkins.authRequired
    && !checkins.loginSuggested
    && !checkins.error
    && recentCheckins.length === 0;

  const incompleteTodos = useMemo(
    () => todos.records.filter((todo) => !asBoolean(todo.completed)).length,
    [todos.records],
  );
  const todayExpenses = useMemo(
    () => overviewLedger.records
      .filter((record) => asText(record.kind) === "expense" && asText(record.local_date) === today)
      .reduce((sum, record) => sum + asNumber(record.amount_cents), 0),
    [overviewLedger.records, today],
  );

  async function ensureHabit(card: HabitCard, index: number): Promise<HabitDefinition | null> {
    const existing = habits.records.find((habit) => asText(habit.title) === card.label);
    if (existing) return existing;
    return habits.create(
      { active: true, iconKey: card.icon, sortOrder: index, title: card.label },
      builtinHabitIdempotencyKey(index),
    );
  }

  async function toggleHabit(card: HabitCard, index: number) {
    if (reference) return;
    setFeedback(`正在处理${card.label}打卡…`);
    setPendingHabitLabel(card.label);
    try {
      const habit = await ensureHabit(card, index);
      if (!habit) {
        setFeedback(`未完成${card.label}打卡：请先登录；使用 Google 登录无需额外验证邮箱，或检查网络后重试。`);
        return;
      }
      const existing = completedByHabitId.get(habit.id);
      if (existing) {
        const removed = await checkins.destroy(existing.id);
        setFeedback(removed ? `已取消${card.label}打卡。` : `未能取消${card.label}打卡，请检查后重试。`);
        return;
      }
      const saved = await checkins.create({ habitId: habit.id, localDate: today });
      setFeedback(
        saved
          ? saveFeedback(
            saved,
            `已完成${card.label}打卡，历史记录已同步。`,
            `已完成${card.label}打卡，记录已保存在当前设备。`,
          )
          : `未完成${card.label}打卡：请先登录；使用 Google 登录无需额外验证邮箱，或检查网络后重试。`,
      );
    } finally {
      setPendingHabitLabel((current) => current === card.label ? null : current);
    }
  }

  async function removeCheckin(checkin: HabitCheckin) {
    const label = habitTitleById.get(asText(checkin.habit_id)) ?? "这条";
    const removed = await checkins.destroy(checkin.id);
    setFeedback(removed ? `已删除${label}的打卡记录。` : `未能删除${label}的打卡记录，请检查后重试。`);
  }

  // Both reads are independent. If one returns the authoritative 401 while
  // the other is interrupted, the local-save state stays visible and the
  // sign-in link remains the next actionable step.
  const authRequired = habits.authRequired || checkins.authRequired;
  const loginSuggested = habits.loginSuggested || checkins.loginSuggested;
  const statusError = habits.error || checkins.error;
  const accountActionRequired = authRequired || loginSuggested;
  const displayTime = reference ? referenceHomeTime : visitorTime;
  const checkinOverview = overviewValue(
    {
      authRequired,
      consentRequired: false,
      error: statusError,
      loading: habits.loading || checkins.loading,
      loginSuggested,
    },
    `${completedLabels.size}/5`,
  );
  const todoOverview = overviewValue(todos, String(incompleteTodos));
  const expenseOverview = overviewValue(overviewLedger, centsToYuan(todayExpenses));

  return (
    <>
      <section className="home-hero">
        <p className="home-greeting">{displayTime?.greeting ?? "正在读取本地问候…"}</p>
        <div className="home-time">{displayTime?.time ?? "正在读取本地时间…"}</div>
        <p className="home-date">{displayTime?.date ?? "正在读取本地日期…"}</p>
        <p className="home-weekday">{displayTime?.weekday ?? ""}</p>
      </section>
      <article className="card quote-card">
        <p className="quote-cn">今天的你，比昨天更优秀。</p>
        <p className="quote-en">You are better today than you were yesterday.</p>
      </article>
      <h2 className="section-title dot">每日打卡</h2>
      <div className="habit-grid">
        {habitCards.map((card, index) => {
          const isCompleted = completedLabels.has(card.label);
          const isPending = pendingHabitLabel === card.label;
          return (
            <button
              aria-busy={isPending}
              aria-pressed={isCompleted}
              className="habit-card"
              // `create` waits for the account/device scope to finish initializing.
              // Do not turn that short read into an inert first tap.
              disabled={!interactionReady || habits.saving || checkins.saving}
              key={card.label}
              onClick={() => void toggleHabit(card, index)}
              type="button"
            >
              <img alt="" className="habit-icon" src={asset(card.icon)} />
              <strong>{card.label}</strong>
              <small>{isCompleted ? "已打卡" : isPending ? "正在保存…" : accountActionRequired ? "本机打卡" : "点击打卡"}</small>
            </button>
          );
        })}
      </div>
      {!reference ? (
        <ResourceStatus
          authRequired={authRequired}
          consentRequired={false}
          error={statusError}
          loginSuggested={loginSuggested}
          loading={habits.loading || checkins.loading}
        />
      ) : null}
      {feedback ? <p className="interaction-note" role="status">{feedback}</p> : null}
      {!reference ? (
        <article className="card record-list-card" aria-live="polite">
          <h2 className="section-title dot">最近打卡</h2>
          {canShowEmptyCheckinHistory ? <div className="empty"><p>还没有打卡历史</p></div> : null}
          <ul className="record-items">
            {recentCheckins.map((checkin) => {
              const label = habitTitleById.get(asText(checkin.habit_id)) ?? "习惯打卡";
              return (
                <li className="record-item" key={checkin.id}>
                  <div><strong>{label}</strong><p>已完成打卡</p></div>
                  <div className="record-meta">
                    <small>{asText(checkin.local_date, "未设置日期")}</small>
                    <DeleteRecordButton disabled={checkins.saving} onDelete={() => void removeCheckin(checkin)} />
                  </div>
                </li>
              );
            })}
          </ul>
        </article>
      ) : null}
      <article className="card overview-card" aria-live="polite">
        <h2 className="section-title dot">今日概览</h2>
        <div className="overview-grid">
          <div className="overview-stat">
            <b>{checkinOverview}</b>
            <span>今日打卡</span>
          </div>
          <div className="overview-stat">
            <b>{todoOverview}</b>
            <span>待办未完成</span>
          </div>
          <div className="overview-stat">
            <b>{expenseOverview}</b>
            <span>今日支出</span>
          </div>
        </div>
      </article>
    </>
  );
}

export function LedgerClient({ fixtureDate, reference }: { fixtureDate: string; reference: boolean }) {
  const ledger = useTenantResource<LedgerRecord>("ledger", { enabled: !reference, sensitive: true });
  const interactionReady = useInteractionReady();
  const [type, setType] = useState<LedgerType>("expense");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("餐饮");
  const [date, setDate] = useState(() => inputDate(fixtureDate, reference));
  const [note, setNote] = useState("");
  const [feedback, setFeedback] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  const income = ledger.records
    .filter((record) => asText(record.kind) === "income")
    .reduce((sum, record) => sum + asNumber(record.amount_cents), 0);
  const expense = ledger.records
    .filter((record) => asText(record.kind) === "expense")
    .reduce((sum, record) => sum + asNumber(record.amount_cents), 0);

  function chooseType(nextType: LedgerType) {
    setType(nextType);
    setFeedback(`当前正在记录${nextType === "expense" ? "支出" : "收入"}。`);
  }

  function startEditing(record: LedgerRecord) {
    const cents = asNumber(record.amount_cents);
    setEditingId(record.id);
    setType(asText(record.kind) === "income" ? "income" : "expense");
    setAmount(cents > 0 ? (cents / 100).toFixed(2) : "");
    setCategory(asText(record.category, "餐饮"));
    setDate(asText(record.local_date, todayIsoDate()));
    setNote(asText(record.note));
    setFeedback("正在编辑这条账单；修改后点击保存修改。");
  }

  async function addRecord() {
    if (reference) return;
    const amountCents = yuanToCents(amount);
    if (!amountCents) {
      setFeedback("请先填写大于 0 的金额，再记一笔。");
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      setFeedback("请按 YYYY-MM-DD 填写日期。");
      return;
    }
    const payload = {
      amountCents,
      category,
      currency: "CNY",
      kind: type,
      localDate: date,
      note: note.trim(),
    };
    const wasEditing = Boolean(editingId);
    setFeedback(wasEditing ? "正在修改账单…" : "正在保存账单…");
    const saved = editingId ? await ledger.update(editingId, payload) : await ledger.create(payload);
    if (!saved) return;
    setAmount("");
    setNote("");
    setEditingId(null);
    setFeedback(saveFeedback(
      saved,
      wasEditing ? "账单已修改，历史账单已更新。" : "已保存，历史账单已更新。",
      wasEditing ? "账单已在当前设备修改。" : "账单已保存在当前设备。",
    ));
  }

  return (
    <>
      <div className="summary-grid" aria-live="polite">
        <div className="summary-card income">
          <span>收入</span>
          <b>+{centsToYuan(income)}</b>
        </div>
        <div className="summary-card expense">
          <span>支出</span>
          <b>-{centsToYuan(expense)}</b>
        </div>
        <div className="summary-card balance">
          <span>结余</span>
          <b>{centsToYuan(income - expense)}</b>
        </div>
      </div>
      <form className="card ledger-form" onSubmit={(event) => event.preventDefault()}>
        <div className="segmented" role="group" aria-label="账目类型">
          <button
            aria-pressed={type === "expense"}
            className={type === "expense" ? "is-active" : ""}
            disabled={!interactionReady}
            onClick={() => chooseType("expense")}
            type="button"
          >
            支出
          </button>
          <button
            aria-pressed={type === "income"}
            className={type === "income" ? "is-active" : ""}
            disabled={!interactionReady}
            onClick={() => chooseType("income")}
            type="button"
          >
            收入
          </button>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>金额</span>
            <input
              className="input"
              inputMode="decimal"
              onChange={(event) => setAmount(event.currentTarget.value)}
              placeholder="0.00"
              value={amount}
            />
          </label>
          <label className="field">
            <span>日期</span>
            <input
              className="input"
              onChange={(event) => setDate(event.currentTarget.value)}
              readOnly={reference}
              value={date}
            />
          </label>
          <label className="field wide">
            <span>分类</span>
            <select className="select" onChange={(event) => setCategory(event.currentTarget.value)} value={category}>
              <option>餐饮</option>
              <option>交通</option>
              <option>购物</option>
              <option>工资</option>
              <option>其他</option>
            </select>
          </label>
          <label className="field wide">
            <span>备注（可选）</span>
            <input className="input" onChange={(event) => setNote(event.currentTarget.value)} placeholder="写点什么…" value={note} />
          </label>
        </div>
        <button className="primary full" disabled={!interactionReady || ledger.saving} onClick={() => void addRecord()} type="button">
          {ledger.saving ? "保存中…" : editingId ? "保存修改" : "＋ 记一笔"}
        </button>
      </form>
      <article className="card record-list-card" aria-live="polite">
        <h2 className="section-title">
          <span aria-hidden="true" className="section-glyph">≡</span>
          账单明细
        </h2>
        {!reference ? <ResourceStatus {...ledger} /> : null}
        {feedback ? <p className="interaction-note" role="status">{feedback}</p> : null}
        {canShowEmptyHistory(ledger, reference) ? (
          <div className="empty"><p>还没有账单，记一笔吧～</p></div>
        ) : null}
        <ul className="record-items">
          {ledger.records.map((record) => (
            <li className="record-item" key={record.id}>
              <div>
                <strong>{asText(record.kind) === "income" ? "收入" : "支出"} {centsToYuan(record.amount_cents)}</strong>
                <p>{asText(record.note, "（无备注）")}</p>
              </div>
              <div className="record-meta">
                <small>{asText(record.category)}</small>
                <small>{asText(record.local_date, "未设置日期")}</small>
                {!reference ? <EditRecordButton disabled={ledger.saving} onEdit={() => startEditing(record)} /> : null}
                {!reference ? <DeleteRecordButton disabled={ledger.saving} onDelete={() => void ledger.destroy(record.id)} /> : null}
              </div>
            </li>
          ))}
        </ul>
      </article>
    </>
  );
}

export function FatlossClient({ fixtureDate, reference }: { fixtureDate: string; reference: boolean }) {
  const foodRecords = useTenantResource<FoodRecord>("food", { enabled: !reference });
  const exerciseRecords = useTenantResource<ExerciseRecord>("exercise", { enabled: !reference });
  const weightRecords = useTenantResource<WeightRecord>("weights", { enabled: !reference, sensitive: true });
  const interactionReady = useInteractionReady();
  const [activeModule, setActiveModule] = useState<FatlossModule>("food");
  const [moduleFeedback, setModuleFeedback] = useState("");
  const [food, setFood] = useState("");
  const [calories, setCalories] = useState("0");
  const [meal, setMeal] = useState("早餐");
  const [date, setDate] = useState(() => inputDate(fixtureDate, reference));
  const [note, setNote] = useState("");
  const [activity, setActivity] = useState("");
  const [durationMinutes, setDurationMinutes] = useState("");
  const [caloriesBurned, setCaloriesBurned] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [uploadFeedback, setUploadFeedback] = useState("");
  const [photoName, setPhotoName] = useState("");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<{
    id: string;
    module: FatlossModule;
    photoObjectId?: string | null;
  } | null>(null);

  const totalCalories = foodRecords.records.reduce((sum, record) => sum + asNumber(record.calories), 0);
  const activeResource = activeModule === "food" ? foodRecords : activeModule === "exercise" ? exerciseRecords : weightRecords;

  function selectModule(nextModule: FatlossModule) {
    if (editing?.module !== nextModule) setEditing(null);
    setActiveModule(nextModule);
    const label = nextModule === "exercise" ? "运动" : nextModule === "weight" ? "体重" : "饮食";
    setModuleFeedback(`已切换到${label}记录。`);
  }

  function startEditingFood(record: FoodRecord) {
    setEditing({ id: record.id, module: "food", photoObjectId: typeof record.photo_object_id === "string" ? record.photo_object_id : null });
    setActiveModule("food");
    setFood(asText(record.food_name));
    setCalories(String(asNumber(record.calories)));
    setMeal(mealLabel(record.meal));
    setDate(asText(record.local_date, todayIsoDate()));
    setNote(asText(record.note));
    setPhotoFile(null);
    setPhotoName(record.photo_object_id ? "已保留原照片（可重新选择）" : "");
    setModuleFeedback("正在编辑这条饮食记录；修改后点击保存修改。");
  }

  function startEditingExercise(record: ExerciseRecord) {
    setEditing({ id: record.id, module: "exercise" });
    setActiveModule("exercise");
    setActivity(asText(record.activity));
    setDurationMinutes(String(asNumber(record.duration_minutes)));
    setCaloriesBurned(record.calories_burned == null ? "" : String(asNumber(record.calories_burned)));
    setDate(asText(record.local_date, todayIsoDate()));
    setNote(asText(record.note));
    setModuleFeedback("正在编辑这条运动记录；修改后点击保存修改。");
  }

  function startEditingWeight(record: WeightRecord) {
    setEditing({ id: record.id, module: "weight" });
    setActiveModule("weight");
    setWeightKg((asNumber(record.weight_grams) / 1000).toFixed(1));
    setDate(asText(record.local_date, todayIsoDate()));
    setNote(asText(record.note));
    setModuleFeedback("正在编辑这条体重记录；修改后点击保存修改。");
  }

  function cancelEditing() {
    setEditing(null);
    setPhotoFile(null);
    setPhotoName("");
    setModuleFeedback("已取消修改，可以继续新增记录。");
  }

  function openPhotoPicker() {
    if (reference) return;
    setUploadFeedback("请选择 JPEG、PNG 或 WebP 格式的食物照片。");
    photoInputRef.current?.click();
  }

  function handlePhotoChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.currentTarget.files?.[0];
    if (!selected) return;
    setPhotoFile(selected);
    setPhotoName(selected.name);
    setUploadFeedback("照片已选好，保存饮食记录时会一起写入你的私有空间。");
  }

  async function uploadFoodPhoto(): Promise<{ id?: string; localOnly?: boolean; ok: boolean }> {
    if (!photoFile) return { ok: true };
    // A guest record has no verified owner for a private file. Preserve the
    // text entry on this device without issuing a known-unauthorized upload.
    // The shared scope resolver also waits through an OAuth-return handoff so
    // a just-signed-in person is not incorrectly downgraded to guest storage.
    if (await resolveBrowserRecordScope() === "guest") {
      setUploadFeedback("照片未上传；饮食文字记录仍会保存在当前设备。");
      return { localOnly: true, ok: true };
    }
    const form = new FormData();
    form.set("module", "food");
    form.set("file", photoFile);
    try {
      const response = await requestWithTimeout(withRequestId("/api/mydairy/files", crypto.randomUUID()), {
        body: form,
        credentials: "same-origin",
        method: "POST",
      });
      if (!response.ok) {
        setUploadFeedback(response.status === 401
          ? "照片未上传；饮食文字记录仍会保存在当前设备。"
          : "照片暂时无法保存；饮食文字记录仍会保存在当前设备。");
        return { localOnly: true, ok: true };
      }
      const value = (await response.json().catch(() => null)) as { data?: { id?: unknown } } | null;
      if (typeof value?.data?.id !== "string") {
        setUploadFeedback("照片保存结果不完整；饮食文字记录仍会保存在当前设备。");
        return { localOnly: true, ok: true };
      }
      return { id: value.data.id, ok: true };
    } catch {
      setUploadFeedback("当前网络不可用，照片未上传；饮食文字记录仍会保存在当前设备。");
      return { localOnly: true, ok: true };
    }
  }

  async function discardUploadedPhoto(id?: string) {
    if (!id) return;
    await requestWithTimeout(withRequestId(`/api/mydairy/files/${encodeURIComponent(id)}`, crypto.randomUUID()), {
      credentials: "same-origin",
      method: "DELETE",
    }).catch(() => undefined);
  }

  async function addFoodRecord() {
    if (reference) return;
    const parsedCalories = Number(calories);
    const normalizedFood = food.trim();
    if (!normalizedFood) {
      setModuleFeedback("请先填写食物名称，再记录饮食。");
      return;
    }
    if (!Number.isSafeInteger(parsedCalories) || parsedCalories < 0 || parsedCalories > 20000) {
      setModuleFeedback("请填写有效的热量数值，再记录饮食。");
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      setModuleFeedback("请按 YYYY-MM-DD 填写日期。");
      return;
    }
    const foodEditing = editing?.module === "food" ? editing : null;
    setModuleFeedback(foodEditing ? "正在修改饮食记录…" : "正在保存饮食记录…");
    const upload = await uploadFoodPhoto();
    if (!upload.ok) return;
    const payload = {
      calories: parsedCalories,
      foodName: normalizedFood,
      localDate: date,
      meal: mealApiValue(meal),
      note: note.trim(),
      photoObjectId: upload.id ?? foodEditing?.photoObjectId ?? null,
      source: "manual",
    };
    const saved = foodEditing ? await foodRecords.update(foodEditing.id, payload) : await foodRecords.create(payload);
    if (!saved) {
      await discardUploadedPhoto(upload.id);
      return;
    }
    let photoNotice = upload.localOnly ? "照片未上传；本条饮食文字记录已保存在当前设备。" : "";
    if (isDeviceLocalRecord(saved) && upload.id) {
      await discardUploadedPhoto(upload.id);
      photoNotice = "照片未随本机记录保存；饮食文字记录已保存在当前设备。";
    }
    setFood("");
    setCalories("0");
    setNote("");
    setPhotoFile(null);
    setPhotoName("");
    setEditing(null);
    setUploadFeedback(photoNotice);
    setModuleFeedback(saveFeedback(
      saved,
      foodEditing ? "饮食记录已修改，历史记录已更新。" : "饮食记录已保存，历史记录已更新。",
      foodEditing ? "饮食记录已在当前设备修改。" : "饮食记录已保存在当前设备。",
    ));
  }

  async function addExerciseRecord() {
    if (reference) return;
    const duration = Number(durationMinutes);
    const burned = caloriesBurned.trim() ? Number(caloriesBurned) : null;
    if (!activity.trim()) {
      setModuleFeedback("请先填写运动项目。");
      return;
    }
    if (!Number.isSafeInteger(duration) || duration < 1 || duration > 1440) {
      setModuleFeedback("请填写 1 到 1440 分钟的运动时长。");
      return;
    }
    if (burned !== null && (!Number.isSafeInteger(burned) || burned < 0 || burned > 20000)) {
      setModuleFeedback("请填写有效的消耗热量，或留空。");
      return;
    }
    const exerciseEditing = editing?.module === "exercise" ? editing : null;
    const payload = {
      activity: activity.trim(),
      caloriesBurned: burned,
      durationMinutes: duration,
      localDate: date,
      note: note.trim(),
    };
    setModuleFeedback(exerciseEditing ? "正在修改运动记录…" : "正在保存运动记录…");
    const saved = exerciseEditing
      ? await exerciseRecords.update(exerciseEditing.id, payload)
      : await exerciseRecords.create(payload);
    if (!saved) return;
    setActivity("");
    setDurationMinutes("");
    setCaloriesBurned("");
    setNote("");
    setEditing(null);
    setModuleFeedback(saveFeedback(
      saved,
      exerciseEditing ? "运动记录已修改，历史记录已更新。" : "运动记录已保存，历史记录已更新。",
      exerciseEditing ? "运动记录已在当前设备修改。" : "运动记录已保存在当前设备。",
    ));
  }

  async function addWeightRecord() {
    if (reference) return;
    const kilograms = Number(weightKg);
    const weightGrams = Math.round(kilograms * 1000);
    if (!Number.isFinite(kilograms) || !Number.isSafeInteger(weightGrams) || weightGrams < 10000 || weightGrams > 500000) {
      setModuleFeedback("请填写 10 到 500 千克之间的体重。");
      return;
    }
    const weightEditing = editing?.module === "weight" ? editing : null;
    const payload = { localDate: date, note: note.trim(), weightGrams };
    setModuleFeedback(weightEditing ? "正在修改体重记录…" : "正在保存体重记录…");
    const saved = weightEditing ? await weightRecords.update(weightEditing.id, payload) : await weightRecords.create(payload);
    if (!saved) return;
    setWeightKg("");
    setNote("");
    setEditing(null);
    setModuleFeedback(saveFeedback(
      saved,
      weightEditing ? "体重记录已修改，历史记录已更新。" : "体重记录已保存，历史记录已更新。",
      weightEditing ? "体重记录已在当前设备修改。" : "体重记录已保存在当前设备。",
    ));
  }

  return (
    <>
      <div className="module-tabs" role="tablist" aria-label="减脂记录类型">
        <button aria-selected={activeModule === "exercise"} className={`module-tab ${activeModule === "exercise" ? "is-active" : ""}`} disabled={!interactionReady} onClick={() => selectModule("exercise")} role="tab" type="button">
          <img alt="" className="module-tab-icon" src={asset("tab_exercise.png")} />运动
        </button>
        <button aria-selected={activeModule === "weight"} className={`module-tab ${activeModule === "weight" ? "is-active" : ""}`} disabled={!interactionReady} onClick={() => selectModule("weight")} role="tab" type="button">
          <img alt="" className="module-tab-icon" src={asset("tab_weight.png")} />体重
        </button>
        <button aria-selected={activeModule === "food"} className={`module-tab ${activeModule === "food" ? "is-active" : ""}`} disabled={!interactionReady} onClick={() => selectModule("food")} role="tab" type="button">
          <img alt="" className="module-tab-icon" src={asset("tab_food.png")} />饮食
        </button>
      </div>
      <form className="card food-card" onSubmit={(event) => event.preventDefault()}>
        <h2 className="section-title">
          <img alt="" src={asset("food_title.png")} />
          {activeModule === "food" ? "饮食记录" : activeModule === "exercise" ? "运动记录" : "体重记录"}
        </h2>
        {activeModule === "food" ? (
          <>
            <label className="field">
              <span>饮食照片（可选，帮您记录）</span>
              <button className="upload-zone" disabled={!interactionReady || foodRecords.saving} onClick={openPhotoPicker} type="button">
                <img alt="" src={asset("food_camera.png")} />
                <span>{photoName || "点击上传食物照片"}</span>
              </button>
              <input accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={handlePhotoChange} ref={photoInputRef} type="file" />
            </label>
            {uploadFeedback ? <p className="interaction-note" role="status">{uploadFeedback}</p> : null}
            <div className="form-grid">
              <label className="field wide"><span>食物</span><select className="select" defaultValue="manual"><option value="manual">-- 手动输入 --</option></select></label>
              <label className="field wide"><span className="sr-only">食物名称</span><input className="input" onChange={(event) => setFood(event.currentTarget.value)} placeholder="输入食物名称" value={food} /></label>
              <label className="field"><span>热量(千卡)</span><input className="input" inputMode="numeric" onChange={(event) => setCalories(event.currentTarget.value)} value={calories} /></label>
              <label className="field"><span>餐次</span><select className="select" onChange={(event) => setMeal(event.currentTarget.value)} value={meal}><option>早餐</option><option>午餐</option><option>晚餐</option><option>加餐</option></select></label>
              <label className="field"><span>日期</span><input className="input" onChange={(event) => setDate(event.currentTarget.value)} readOnly={reference} value={date} /></label>
              <label className="field"><span>备注</span><input className="input" onChange={(event) => setNote(event.currentTarget.value)} placeholder="可选" value={note} /></label>
            </div>
            <button className="primary full" disabled={!interactionReady || foodRecords.saving} onClick={() => void addFoodRecord()} type="button">{foodRecords.saving ? "保存中…" : editing?.module === "food" ? "保存修改" : "＋ 记录饮食"}</button>
          </>
        ) : activeModule === "exercise" ? (
          <div className="form-grid">
            <label className="field wide"><span>运动项目</span><input className="input" onChange={(event) => setActivity(event.currentTarget.value)} placeholder="例如：慢跑" value={activity} /></label>
            <label className="field"><span>时长（分钟）</span><input className="input" inputMode="numeric" onChange={(event) => setDurationMinutes(event.currentTarget.value)} value={durationMinutes} /></label>
            <label className="field"><span>消耗热量（可选）</span><input className="input" inputMode="numeric" onChange={(event) => setCaloriesBurned(event.currentTarget.value)} value={caloriesBurned} /></label>
            <label className="field"><span>日期</span><input className="input" onChange={(event) => setDate(event.currentTarget.value)} readOnly={reference} value={date} /></label>
            <label className="field wide"><span>备注</span><input className="input" onChange={(event) => setNote(event.currentTarget.value)} placeholder="可选" value={note} /></label>
            <button className="primary full" disabled={!interactionReady || exerciseRecords.saving} onClick={() => void addExerciseRecord()} type="button">{exerciseRecords.saving ? "保存中…" : editing?.module === "exercise" ? "保存修改" : "＋ 记录运动"}</button>
          </div>
        ) : (
          <div className="form-grid">
            <label className="field"><span>体重（千克）</span><input className="input" inputMode="decimal" onChange={(event) => setWeightKg(event.currentTarget.value)} placeholder="例如：52.3" value={weightKg} /></label>
            <label className="field"><span>日期</span><input className="input" onChange={(event) => setDate(event.currentTarget.value)} readOnly={reference} value={date} /></label>
            <label className="field wide"><span>备注</span><input className="input" onChange={(event) => setNote(event.currentTarget.value)} placeholder="可选" value={note} /></label>
            <button className="primary full" disabled={!interactionReady || weightRecords.saving} onClick={() => void addWeightRecord()} type="button">{weightRecords.saving ? "保存中…" : editing?.module === "weight" ? "保存修改" : "＋ 记录体重"}</button>
          </div>
        )}
        {editing?.module === activeModule ? <button className="auth-secondary-link" onClick={cancelEditing} type="button">取消修改</button> : null}
        {moduleFeedback ? <p className="interaction-note" role="status">{moduleFeedback}</p> : null}
      </form>
      <article className="total-card" aria-live="polite"><span>今日摄入总热量</span><b>{totalCalories}</b><span>千卡</span></article>
      <section className="card record-list-card" aria-live="polite">
        <h2 className="section-title">{activeModule === "food" ? "饮食历史" : activeModule === "exercise" ? "运动历史" : "体重历史"}</h2>
        {!reference ? <ResourceStatus {...activeResource} /> : null}
        {canShowEmptyHistory(activeResource, reference) ? <div className="empty"><p>还没有历史记录</p></div> : null}
        <ul className="record-items">
          {activeModule === "food" ? foodRecords.records.map((record) => (
            <li className="record-item" key={record.id}><div><strong>{asText(record.food_name)}</strong><p>{mealLabel(record.meal)} · {asNumber(record.calories)} 千卡</p></div><div className="record-meta"><small>{asText(record.local_date)}</small>{!reference ? <EditRecordButton disabled={foodRecords.saving} onEdit={() => startEditingFood(record)} /> : null}{!reference ? <DeleteRecordButton disabled={foodRecords.saving} onDelete={() => void foodRecords.destroy(record.id)} /> : null}</div></li>
          )) : null}
          {activeModule === "exercise" ? exerciseRecords.records.map((record) => (
            <li className="record-item" key={record.id}><div><strong>{asText(record.activity)}</strong><p>{asNumber(record.duration_minutes)} 分钟{record.calories_burned == null ? "" : ` · ${asNumber(record.calories_burned)} 千卡`}</p></div><div className="record-meta"><small>{asText(record.local_date)}</small>{!reference ? <EditRecordButton disabled={exerciseRecords.saving} onEdit={() => startEditingExercise(record)} /> : null}{!reference ? <DeleteRecordButton disabled={exerciseRecords.saving} onDelete={() => void exerciseRecords.destroy(record.id)} /> : null}</div></li>
          )) : null}
          {activeModule === "weight" ? weightRecords.records.map((record) => (
            <li className="record-item" key={record.id}><div><strong>{(asNumber(record.weight_grams) / 1000).toFixed(1)} 千克</strong><p>{asText(record.note, "（无备注）")}</p></div><div className="record-meta"><small>{asText(record.local_date)}</small>{!reference ? <EditRecordButton disabled={weightRecords.saving} onEdit={() => startEditingWeight(record)} /> : null}{!reference ? <DeleteRecordButton disabled={weightRecords.saving} onDelete={() => void weightRecords.destroy(record.id)} /> : null}</div></li>
          )) : null}
        </ul>
      </section>
    </>
  );
}

export function PeriodClient({ reference }: { reference: boolean }) {
  const periods = useTenantResource<PeriodRecord>("periods", { enabled: !reference, sensitive: true });
  const interactionReady = useInteractionReady();
  const [startDate, setStartDate] = useState(() => (reference ? "" : todayIsoDate()));
  const [endDate, setEndDate] = useState(() => (reference ? "" : todayIsoDate()));
  const [note, setNote] = useState("");
  const [feedback, setFeedback] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  function startEditing(record: PeriodRecord) {
    setEditingId(record.id);
    setStartDate(asText(record.start_date, todayIsoDate()));
    setEndDate(asText(record.end_date, todayIsoDate()));
    setNote(asText(record.note));
    setFeedback("正在编辑这条经期记录；修改后点击保存修改。");
  }

  async function addPeriodRecord() {
    if (reference) return;
    const start = startDate.trim();
    const end = endDate.trim() || start;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
      setFeedback("请按 YYYY-MM-DD 填写开始和结束日期。");
      return;
    }
    if (end < start) {
      setFeedback("结束日期不能早于开始日期。");
      return;
    }
    setFeedback("正在保存经期记录…");
    const payload = { endDate: end, note: note.trim(), startDate: start };
    const wasEditing = Boolean(editingId);
    const saved = editingId ? await periods.update(editingId, payload) : await periods.create(payload);
    if (!saved) {
      setFeedback("未能保存经期记录，请查看上方状态提示后重试。");
      return;
    }
    setStartDate(todayIsoDate());
    setEndDate(todayIsoDate());
    setNote("");
    setEditingId(null);
    setFeedback(saveFeedback(
      saved,
      wasEditing ? "经期记录已修改，历史记录已更新。" : "经期记录已保存，历史记录已更新。",
      wasEditing ? "经期记录已在当前设备修改。" : "经期记录已保存在当前设备。",
    ));
  }

  return (
    <>
      <form className="card period-form" onSubmit={(event) => event.preventDefault()}>
        <div className="form-grid">
          <label className="field"><span>开始日期</span><input className="input" onChange={(event) => setStartDate(event.currentTarget.value)} readOnly={reference} value={startDate} /></label>
          <label className="field"><span>结束日期</span><input className="input" onChange={(event) => setEndDate(event.currentTarget.value)} readOnly={reference} value={endDate} /></label>
        </div>
        <button className="primary full" disabled={!interactionReady || periods.saving} onClick={() => void addPeriodRecord()} type="button">{periods.saving ? "保存中…" : editingId ? "保存修改" : "＋ 记录经期"}</button>
      </form>
      <article className="card period-overview">
        <h2 className="section-title"><img alt="" src={asset("period_title.png")} />周期概览</h2>
        <div className="period-stats"><div className="period-stat"><span>当前周期</span><b>--</b></div><div className="period-stat"><span>预测下次（估算）</span><b>--</b></div><div className="period-stat"><span>平均周期</span><b>--</b></div></div>
      </article>
      <article className="card period-history" aria-live="polite">
        <h2 className="section-title"><span aria-hidden="true" className="section-glyph">≡</span>历史记录</h2>
        {!reference ? <ResourceStatus {...periods} /> : null}
        {feedback ? <p className="interaction-note" role="status">{feedback}</p> : null}
        {canShowEmptyHistory(periods, reference) ? <div className="empty"><p>还没有经期记录</p></div> : null}
        <ul className="record-items">
          {periods.records.map((record) => (
            <li className="record-item" key={record.id}><div><strong>{asText(record.start_date)} 至 {asText(record.end_date)}</strong><p>{asText(record.note, "（无备注）")}</p></div><div className="record-meta">{!reference ? <EditRecordButton disabled={periods.saving} onEdit={() => startEditing(record)} /> : null}{!reference ? <DeleteRecordButton disabled={periods.saving} onDelete={() => void periods.destroy(record.id)} /> : null}</div></li>
          ))}
        </ul>
      </article>
    </>
  );
}

type GenericRoute = "schedule" | "anniversary" | "diary" | "savings";

function asDateTimeInput(value: unknown): string {
  const timestamp = asNumber(value, Number.NaN);
  if (!Number.isFinite(timestamp)) return "";
  const date = new Date(timestamp);
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(timestamp - offset).toISOString().slice(0, 16);
}

function fromDateTimeInput(value: string): number | null {
  if (!value) return null;
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}

function genericRecordTitle(record: TenantRecord): string {
  return asText(record.title) || asText(record.body) || "未命名记录";
}

export function GenericPageClient({
  label,
  reference,
  route,
}: {
  label: string;
  reference: boolean;
  route: GenericRoute;
}) {
  const schedule = useTenantResource<ScheduleRecord>("schedule", { enabled: !reference && route === "schedule" });
  const anniversaries = useTenantResource<AnniversaryRecord>("anniversaries", { enabled: !reference && route === "anniversary" });
  const diary = useTenantResource<DiaryRecord>("diary", { enabled: !reference && route === "diary", sensitive: true });
  const savingsGoals = useTenantResource<SavingsGoalRecord>("savings-goals", { enabled: !reference && route === "savings" });
  const savingsTransactions = useTenantResource<SavingsTransactionRecord>("savings-transactions", { enabled: !reference && route === "savings" });
  const interactionReady = useInteractionReady();
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [date, setDate] = useState(() => todayIsoDate());
  const [startsAt, setStartsAt] = useState(() => asDateTimeInput(Date.now()));
  const [repeatYearly, setRepeatYearly] = useState(true);
  const [mood, setMood] = useState("");
  const [body, setBody] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [goalId, setGoalId] = useState("");
  const [transactionAmount, setTransactionAmount] = useState("");
  const [feedback, setFeedback] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingKind, setEditingKind] = useState<"primary" | "transaction" | null>(null);

  const current = route === "schedule"
    ? schedule
    : route === "anniversary"
      ? anniversaries
      : route === "diary"
        ? diary
      : savingsGoals;

  const primaryEditing = editingKind === "primary" && Boolean(editingId);
  const transactionEditing = editingKind === "transaction" && Boolean(editingId);

  function clearPrimaryFields() {
    setTitle("");
    setNote("");
    setMood("");
    setBody("");
    setTargetAmount("");
    setTargetDate("");
  }

  function startEditingPrimary(record: TenantRecord) {
    setEditingId(record.id);
    setEditingKind("primary");
    if (route === "schedule") {
      setTitle(asText(record.title));
      setNote(asText(record.note));
      setStartsAt(asDateTimeInput(record.starts_at) || startsAt);
    } else if (route === "anniversary") {
      setTitle(asText(record.title));
      setDate(asText(record.local_date, todayIsoDate()));
      setRepeatYearly(asBoolean(record.repeat_yearly, true));
      setNote(asText(record.note));
    } else if (route === "diary") {
      setTitle(asText(record.title));
      setDate(asText(record.local_date, todayIsoDate()));
      setMood(asText(record.mood));
      setBody(asText(record.body));
    } else {
      const cents = asNumber(record.target_cents);
      setTitle(asText(record.title));
      setTargetAmount(cents > 0 ? (cents / 100).toFixed(2) : "");
      setTargetDate(asText(record.target_date));
    }
    setFeedback("正在编辑这条记录；修改后点击保存修改。");
  }

  function startEditingTransaction(record: SavingsTransactionRecord) {
    const cents = asNumber(record.amount_cents);
    setEditingId(record.id);
    setEditingKind("transaction");
    setGoalId(asText(record.goal_id));
    setTransactionAmount(cents !== 0 ? (cents / 100).toFixed(2) : "");
    setDate(asText(record.local_date, todayIsoDate()));
    setNote(asText(record.note));
    setFeedback("正在编辑这条存入记录；修改后点击保存修改。");
  }

  function cancelEditing() {
    setEditingId(null);
    setEditingKind(null);
    clearPrimaryFields();
    setTransactionAmount("");
    setFeedback("已取消修改，可以继续新增记录。");
  }

  async function submitSchedule() {
    const timestamp = fromDateTimeInput(startsAt);
    if (!title.trim()) {
      setFeedback("请先填写日程标题。");
      return;
    }
    if (timestamp === null) {
      setFeedback("请填写有效的开始时间。");
      return;
    }
    const payload = { allDay: false, note: note.trim(), startsAt: timestamp, title: title.trim() };
    const editingRecordId = editingKind === "primary" ? editingId : null;
    setFeedback(editingRecordId ? "正在修改日程…" : "正在保存日程…");
    const saved = editingRecordId ? await schedule.update(editingRecordId, payload) : await schedule.create(payload);
    if (!saved) return;
    const wasEditing = Boolean(editingRecordId);
    setEditingId(null);
    setEditingKind(null);
    clearPrimaryFields();
    setFeedback(saveFeedback(
      saved,
      wasEditing ? "日程已修改，历史列表已更新。" : "日程已保存，历史列表已更新。",
      wasEditing ? "日程已在当前设备修改。" : "日程已保存在当前设备。",
    ));
  }

  async function submitAnniversary() {
    if (!title.trim()) {
      setFeedback("请先填写纪念日名称。");
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      setFeedback("请按 YYYY-MM-DD 填写日期。");
      return;
    }
    const payload = { localDate: date, note: note.trim(), repeatYearly, title: title.trim() };
    const editingRecordId = editingKind === "primary" ? editingId : null;
    setFeedback(editingRecordId ? "正在修改纪念日…" : "正在保存纪念日…");
    const saved = editingRecordId ? await anniversaries.update(editingRecordId, payload) : await anniversaries.create(payload);
    if (!saved) return;
    const wasEditing = Boolean(editingRecordId);
    setEditingId(null);
    setEditingKind(null);
    clearPrimaryFields();
    setFeedback(saveFeedback(
      saved,
      wasEditing ? "纪念日已修改，历史列表已更新。" : "纪念日已保存，历史列表已更新。",
      wasEditing ? "纪念日已在当前设备修改。" : "纪念日已保存在当前设备。",
    ));
  }

  async function submitDiary() {
    if (!body.trim()) {
      setFeedback("请先写下日记内容。");
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      setFeedback("请按 YYYY-MM-DD 填写日期。");
      return;
    }
    const payload = { body: body.trim(), localDate: date, mood: mood.trim(), title: title.trim() };
    const editingRecordId = editingKind === "primary" ? editingId : null;
    setFeedback(editingRecordId ? "正在修改日记…" : "正在保存日记…");
    const saved = editingRecordId ? await diary.update(editingRecordId, payload) : await diary.create(payload);
    if (!saved) return;
    const wasEditing = Boolean(editingRecordId);
    setEditingId(null);
    setEditingKind(null);
    clearPrimaryFields();
    setFeedback(saveFeedback(
      saved,
      wasEditing ? "日记已修改，历史列表已更新。" : "日记已保存，历史列表已更新。",
      wasEditing ? "日记已在当前设备修改。" : "日记已保存在当前设备。",
    ));
  }

  async function submitSavingsGoal() {
    const targetCents = yuanToCents(targetAmount);
    if (!title.trim()) {
      setFeedback("请先填写计划名称。");
      return;
    }
    if (!targetCents) {
      setFeedback("请填写大于 0 的目标金额。");
      return;
    }
    if (targetDate && !/^\d{4}-\d{2}-\d{2}$/.test(targetDate)) {
      setFeedback("请按 YYYY-MM-DD 填写目标日期，或留空。");
      return;
    }
    const payload = { archived: false, currency: "CNY", targetCents, targetDate: targetDate || null, title: title.trim() };
    const editingRecordId = editingKind === "primary" ? editingId : null;
    setFeedback(editingRecordId ? "正在修改存钱计划…" : "正在保存存钱计划…");
    const saved = editingRecordId ? await savingsGoals.update(editingRecordId, payload) : await savingsGoals.create(payload);
    if (!saved) return;
    const wasEditing = Boolean(editingRecordId);
    setEditingId(null);
    setEditingKind(null);
    clearPrimaryFields();
    setGoalId(saved.id);
    setFeedback(saveFeedback(
      saved,
      wasEditing ? "存钱计划已修改，可以继续记录存入金额。" : "存钱计划已保存，可以继续记录存入金额。",
      wasEditing ? "存钱计划已在当前设备修改。" : "存钱计划已保存在当前设备，可以继续记录存入金额。",
    ));
  }

  async function submitSavingsTransaction() {
    const amountCents = yuanToCents(transactionAmount);
    const selectedGoalId = goalId || savingsGoals.records[0]?.id;
    if (!selectedGoalId) {
      setFeedback("请先新增一个存钱计划。");
      return;
    }
    if (!amountCents) {
      setFeedback("请填写大于 0 的存入金额。");
      return;
    }
    const payload = { amountCents, goalId: selectedGoalId, localDate: date, note: note.trim() };
    const editingRecordId = editingKind === "transaction" ? editingId : null;
    setFeedback(editingRecordId ? "正在修改存入记录…" : "正在保存存入记录…");
    const saved = editingRecordId
      ? await savingsTransactions.update(editingRecordId, payload)
      : await savingsTransactions.create(payload);
    if (!saved) return;
    const wasEditing = Boolean(editingRecordId);
    setEditingId(null);
    setEditingKind(null);
    setTransactionAmount("");
    setNote("");
    setFeedback(saveFeedback(
      saved,
      wasEditing ? "存入记录已修改，历史列表已更新。" : "存入记录已保存，历史列表已更新。",
      wasEditing ? "存入记录已在当前设备修改。" : "存入记录已保存在当前设备。",
    ));
  }

  const action = route === "schedule"
    ? submitSchedule
    : route === "anniversary"
      ? submitAnniversary
      : route === "diary"
        ? submitDiary
        : submitSavingsGoal;

  return (
    <>
      <article className="card generic-card" aria-live="polite">
        <p className="muted">把今天真正要完成的小事，温柔地放在这里。</p>
        {route === "schedule" ? (
          <div className="field-form">
            <div className="form-grid">
              <label className="field wide"><span>日程标题</span><input className="input" maxLength={200} onChange={(event) => setTitle(event.currentTarget.value)} value={title} /></label>
              <label className="field wide"><span>开始时间</span><input className="input" onChange={(event) => setStartsAt(event.currentTarget.value)} type="datetime-local" value={startsAt} /></label>
              <label className="field wide"><span>备注</span><input className="input" maxLength={5000} onChange={(event) => setNote(event.currentTarget.value)} value={note} /></label>
            </div>
          </div>
        ) : null}
        {route === "anniversary" ? (
          <div className="field-form">
            <div className="form-grid">
              <label className="field wide"><span>纪念日名称</span><input className="input" maxLength={160} onChange={(event) => setTitle(event.currentTarget.value)} value={title} /></label>
              <label className="field"><span>日期</span><input className="input" onChange={(event) => setDate(event.currentTarget.value)} value={date} /></label>
              <label className="field"><span>重复方式</span><select className="select" onChange={(event) => setRepeatYearly(event.currentTarget.value === "yes")} value={repeatYearly ? "yes" : "no"}><option value="yes">每年重复</option><option value="no">仅一次</option></select></label>
              <label className="field wide"><span>备注</span><input className="input" maxLength={2000} onChange={(event) => setNote(event.currentTarget.value)} value={note} /></label>
            </div>
          </div>
        ) : null}
        {route === "diary" ? (
          <div className="field-form">
            <div className="form-grid">
              <label className="field"><span>日期</span><input className="input" onChange={(event) => setDate(event.currentTarget.value)} value={date} /></label>
              <label className="field"><span>心情（可选）</span><input className="input" maxLength={80} onChange={(event) => setMood(event.currentTarget.value)} value={mood} /></label>
              <label className="field wide"><span>标题（可选）</span><input className="input" maxLength={200} onChange={(event) => setTitle(event.currentTarget.value)} value={title} /></label>
              <label className="field wide"><span>日记内容</span><textarea className="input generic-textarea" maxLength={30000} onChange={(event) => setBody(event.currentTarget.value)} value={body} /></label>
            </div>
          </div>
        ) : null}
        {route === "savings" ? (
          <div className="field-form">
            <div className="form-grid">
              <label className="field wide"><span>计划名称</span><input className="input" maxLength={160} onChange={(event) => setTitle(event.currentTarget.value)} placeholder="例如：旅行基金" value={title} /></label>
              <label className="field"><span>目标金额</span><input className="input" inputMode="decimal" onChange={(event) => setTargetAmount(event.currentTarget.value)} placeholder="0.00" value={targetAmount} /></label>
              <label className="field"><span>目标日期（可选）</span><input className="input" onChange={(event) => setTargetDate(event.currentTarget.value)} placeholder="YYYY-MM-DD" value={targetDate} /></label>
            </div>
          </div>
        ) : null}
        <button className="primary full" disabled={reference || !interactionReady || current.saving} onClick={() => void action()} type="button">
          {current.saving ? "保存中…" : primaryEditing ? "保存修改" : route === "savings" ? "＋ 新增存钱计划" : "＋ 新增记录"}
        </button>
        {primaryEditing ? <button className="auth-secondary-link" onClick={cancelEditing} type="button">取消修改</button> : null}
        {!reference ? <ResourceStatus {...current} /> : null}
        {feedback ? <p className="interaction-note" role="status">{feedback}</p> : null}
      </article>

      {route === "savings" && savingsGoals.records.length > 0 ? (
        <article className="card generic-card savings-transaction-card" aria-live="polite">
          <h2 className="section-title">记录存入</h2>
          <div className="field-form"><div className="form-grid">
            <label className="field wide"><span>存钱计划</span><select className="select" onChange={(event) => setGoalId(event.currentTarget.value)} value={goalId || savingsGoals.records[0]?.id || ""}>{savingsGoals.records.map((goal) => <option key={goal.id} value={goal.id}>{asText(goal.title)}</option>)}</select></label>
            <label className="field"><span>存入金额</span><input className="input" inputMode="decimal" onChange={(event) => setTransactionAmount(event.currentTarget.value)} placeholder="0.00" value={transactionAmount} /></label>
            <label className="field"><span>日期</span><input className="input" onChange={(event) => setDate(event.currentTarget.value)} value={date} /></label>
            <label className="field wide"><span>备注</span><input className="input" maxLength={1000} onChange={(event) => setNote(event.currentTarget.value)} value={note} /></label>
          </div></div>
          <button className="primary full" disabled={reference || !interactionReady || savingsTransactions.saving} onClick={() => void submitSavingsTransaction()} type="button">{savingsTransactions.saving ? "保存中…" : transactionEditing ? "保存修改" : "＋ 记录存入"}</button>
          {transactionEditing ? <button className="auth-secondary-link" onClick={cancelEditing} type="button">取消修改</button> : null}
          {!reference ? <ResourceStatus {...savingsTransactions} /> : null}
        </article>
      ) : null}

      <article className="card record-list-card" aria-live="polite">
        <h2 className="section-title"><span aria-hidden="true" className="section-glyph">≡</span>{label}历史记录</h2>
        {canShowEmptyHistory(current, reference) ? <div className="empty"><p>还没有历史记录，新增一条吧～</p></div> : null}
        <ul className="record-items">
          {route === "schedule" ? schedule.records.map((record) => <li className="record-item" key={record.id}><div><strong>{genericRecordTitle(record)}</strong><p>{asText(record.note, "（无备注）")}</p></div><div className="record-meta"><small>{asDateTimeInput(record.starts_at).replace("T", " ")}</small>{!reference ? <EditRecordButton disabled={schedule.saving} onEdit={() => startEditingPrimary(record)} /> : null}{!reference ? <DeleteRecordButton disabled={schedule.saving} onDelete={() => void schedule.destroy(record.id)} /> : null}</div></li>) : null}
          {route === "anniversary" ? anniversaries.records.map((record) => <li className="record-item" key={record.id}><div><strong>{genericRecordTitle(record)}</strong><p>{asText(record.note, "（无备注）")}</p></div><div className="record-meta"><small>{asText(record.local_date)}{record.repeat_yearly ? " · 每年" : ""}</small>{!reference ? <EditRecordButton disabled={anniversaries.saving} onEdit={() => startEditingPrimary(record)} /> : null}{!reference ? <DeleteRecordButton disabled={anniversaries.saving} onDelete={() => void anniversaries.destroy(record.id)} /> : null}</div></li>) : null}
          {route === "diary" ? diary.records.map((record) => <li className="record-item" key={record.id}><div><strong>{genericRecordTitle(record)}</strong><p>{asText(record.body)}</p></div><div className="record-meta"><small>{asText(record.local_date)}{asText(record.mood) ? ` · ${asText(record.mood)}` : ""}</small>{!reference ? <EditRecordButton disabled={diary.saving} onEdit={() => startEditingPrimary(record)} /> : null}{!reference ? <DeleteRecordButton disabled={diary.saving} onDelete={() => void diary.destroy(record.id)} /> : null}</div></li>) : null}
          {route === "savings" ? savingsGoals.records.map((record) => {
            const saved = savingsTransactions.records.filter((entry) => asText(entry.goal_id) === record.id).reduce((sum, entry) => sum + asNumber(entry.amount_cents), 0);
            return <li className="record-item" key={record.id}><div><strong>{asText(record.title)}</strong><p>已存 {centsToYuan(saved)} / 目标 {centsToYuan(record.target_cents)}</p></div><div className="record-meta"><small>{asText(record.target_date, "未设置日期")}</small>{!reference ? <EditRecordButton disabled={savingsGoals.saving} onEdit={() => startEditingPrimary(record)} /> : null}{!reference ? <DeleteRecordButton disabled={savingsGoals.saving} onDelete={() => void savingsGoals.destroy(record.id)} /> : null}</div></li>;
          }) : null}
          {route === "savings" ? savingsTransactions.records.map((record) => <li className="record-item" key={record.id}><div><strong>存入 {centsToYuan(record.amount_cents)}</strong><p>{asText(record.note, "（无备注）")}</p></div><div className="record-meta"><small>{asText(record.local_date)}</small>{!reference ? <EditRecordButton disabled={savingsTransactions.saving} onEdit={() => startEditingTransaction(record)} /> : null}{!reference ? <DeleteRecordButton disabled={savingsTransactions.saving} onDelete={() => void savingsTransactions.destroy(record.id)} /> : null}</div></li>) : null}
        </ul>
      </article>
    </>
  );
}
