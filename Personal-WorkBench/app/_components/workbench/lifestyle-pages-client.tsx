"use client";

/* eslint-disable @next/next/no-img-element */

import { ChangeEvent, useRef, useState } from "react";

const PRIVATE_ASSET_ROOT = "/private-reference-assets";
const RUNTIME_ASSET_ROOT = `${PRIVATE_ASSET_ROOT}/runtime`;

type HabitCard = {
  icon: string;
  label: string;
};

type LedgerType = "expense" | "income";

type LedgerRecord = {
  amount: number;
  category: string;
  date: string;
  id: string;
  note: string;
  type: LedgerType;
};

type FoodRecord = {
  calories: number;
  food: string;
  id: string;
  meal: string;
};

type FatlossModule = "exercise" | "weight" | "food";

function asset(name: string) {
  return `${RUNTIME_ASSET_ROOT}/${name}`;
}

function recordId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function amountLabel(amount: number) {
  return `¥${amount.toFixed(2)}`;
}

export function HomeClient({ habitCards }: { habitCards: HabitCard[] }) {
  const [completed, setCompleted] = useState<Set<string>>(() => new Set());

  function toggleHabit(label: string) {
    setCompleted((current) => {
      const next = new Set(current);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }

  return (
    <>
      <section className="home-hero">
        <p className="home-greeting">早上好，小张张～</p>
        <div className="home-time">11:27</div>
        <p className="home-date">2026年8月2日</p>
        <p className="home-weekday">星期日</p>
      </section>
      <article className="card quote-card">
        <p className="quote-cn">今天的你，比昨天更优秀。</p>
        <p className="quote-en">You are better today than you were yesterday.</p>
      </article>
      <h2 className="section-title dot">每日打卡</h2>
      <div className="habit-grid">
        {habitCards.map(({ icon, label }) => {
          const isCompleted = completed.has(label);
          return (
            <button
              aria-pressed={isCompleted}
              className="habit-card"
              key={label}
              onClick={() => toggleHabit(label)}
              type="button"
            >
              <img alt="" className="habit-icon" src={asset(icon)} />
              <strong>{label}</strong>
              <small>{isCompleted ? "已打卡" : "点击打卡"}</small>
            </button>
          );
        })}
      </div>
      <article className="card overview-card" aria-live="polite">
        <h2 className="section-title dot">今日概览</h2>
        <div className="overview-grid">
          <div className="overview-stat">
            <b>{completed.size}/5</b>
            <span>今日打卡</span>
          </div>
          <div className="overview-stat">
            <b>0</b>
            <span>待办未完成</span>
          </div>
          <div className="overview-stat">
            <b>¥0.00</b>
            <span>今日支出</span>
          </div>
        </div>
      </article>
    </>
  );
}

export function LedgerClient({ fixtureDate, reference }: { fixtureDate: string; reference: boolean }) {
  const [type, setType] = useState<LedgerType>("expense");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("餐饮");
  const [date, setDate] = useState(fixtureDate);
  const [note, setNote] = useState("");
  const [feedback, setFeedback] = useState("");
  const [records, setRecords] = useState<LedgerRecord[]>([]);

  const income = records.filter((record) => record.type === "income").reduce((sum, record) => sum + record.amount, 0);
  const expense = records.filter((record) => record.type === "expense").reduce((sum, record) => sum + record.amount, 0);

  function chooseType(nextType: LedgerType) {
    setType(nextType);
    setFeedback(`当前正在记录${nextType === "expense" ? "支出" : "收入"}。`);
  }

  function addRecord() {
    const parsedAmount = Number.parseFloat(amount);
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setFeedback("请先填写大于 0 的金额，再记一笔。");
      return;
    }

    setRecords((current) => [
      {
        amount: parsedAmount,
        category,
        date,
        id: recordId(),
        note: note.trim(),
        type,
      },
      ...current,
    ]);
    setAmount("");
    setNote("");
    setFeedback("已保存到当前会话；登录后可同步到工作台。");
  }

  return (
    <>
      <div className="summary-grid" aria-live="polite">
        <div className="summary-card income">
          <span>收入</span>
          <b>+{amountLabel(income)}</b>
        </div>
        <div className="summary-card expense">
          <span>支出</span>
          <b>-{amountLabel(expense)}</b>
        </div>
        <div className="summary-card balance">
          <span>结余</span>
          <b>{amountLabel(income - expense)}</b>
        </div>
      </div>
      <form className="card ledger-form" onSubmit={(event) => event.preventDefault()}>
        <div className="segmented" role="group" aria-label="账目类型">
          <button
            aria-pressed={type === "expense"}
            className={type === "expense" ? "is-active" : ""}
            onClick={() => chooseType("expense")}
            type="button"
          >
            支出
          </button>
          <button
            aria-pressed={type === "income"}
            className={type === "income" ? "is-active" : ""}
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
        <button className="primary full" onClick={addRecord} type="button">
          ＋ 记一笔
        </button>
      </form>
      <article className="card record-list-card" aria-live="polite">
        <h2 className="section-title">
          <span aria-hidden="true" className="section-glyph">
            ≡
          </span>
          账单明细
        </h2>
        {feedback ? <p className="interaction-note" role="status">{feedback}</p> : null}
        {records.length === 0 ? (
          <div className="empty">
            <p>还没有账单，记一笔吧～</p>
          </div>
        ) : (
          <ul className="record-items">
            {records.map((record) => (
              <li className="record-item" key={record.id}>
                <div>
                  <strong>{record.type === "expense" ? "支出" : "收入"} {amountLabel(record.amount)}</strong>
                  <p>{record.note || "（无备注）"}</p>
                </div>
                <div className="record-meta">
                  <small>{record.category}</small>
                  <small>{record.date || "未设置日期"}</small>
                </div>
              </li>
            ))}
          </ul>
        )}
      </article>
    </>
  );
}

export function FatlossClient({ fixtureDate, reference }: { fixtureDate: string; reference: boolean }) {
  const [activeModule, setActiveModule] = useState<FatlossModule>("food");
  const [moduleFeedback, setModuleFeedback] = useState("");
  const [food, setFood] = useState("");
  const [calories, setCalories] = useState("0");
  const [meal, setMeal] = useState("早餐");
  const [date, setDate] = useState(fixtureDate);
  const [note, setNote] = useState("");
  const [foodRecords, setFoodRecords] = useState<FoodRecord[]>([]);
  const [uploadFeedback, setUploadFeedback] = useState("");
  const [photoName, setPhotoName] = useState("");
  const photoInputRef = useRef<HTMLInputElement>(null);

  const totalCalories = foodRecords.reduce((sum, record) => sum + record.calories, 0);

  function selectModule(nextModule: FatlossModule) {
    setActiveModule(nextModule);
    const label = nextModule === "exercise" ? "运动" : nextModule === "weight" ? "体重" : "饮食";
    setModuleFeedback(`已切换到${label}记录。`);
  }

  function openPhotoPicker() {
    setUploadFeedback("已打开文件选择器；选择图片后会显示文件名，登录后才会写入私有存储。");
    photoInputRef.current?.click();
  }

  function handlePhotoChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.currentTarget.files?.[0];
    if (!selected) return;
    setPhotoName(selected.name);
    setUploadFeedback("已选择食物照片；当前仅暂存在本次会话。登录后可上传到私有存储。");
  }

  function addFoodRecord() {
    const parsedCalories = Number.parseFloat(calories);
    const normalizedFood = food.trim();
    if (!normalizedFood) {
      setModuleFeedback("请先填写食物名称，再记录饮食。");
      return;
    }
    if (!Number.isFinite(parsedCalories) || parsedCalories < 0) {
      setModuleFeedback("请填写有效的热量数值，再记录饮食。");
      return;
    }

    setFoodRecords((current) => [
      { calories: parsedCalories, food: normalizedFood, id: recordId(), meal },
      ...current,
    ]);
    setFood("");
    setCalories("0");
    setNote("");
    setModuleFeedback("饮食记录已保存到当前会话；登录后可同步到工作台。");
  }

  return (
    <>
      <div className="module-tabs" role="tablist" aria-label="减脂记录类型">
        <button
          aria-selected={activeModule === "exercise"}
          className={`module-tab ${activeModule === "exercise" ? "is-active" : ""}`}
          onClick={() => selectModule("exercise")}
          role="tab"
          type="button"
        >
          <img alt="" className="module-tab-icon" src={asset("tab_exercise.png")} />
          运动
        </button>
        <button
          aria-selected={activeModule === "weight"}
          className={`module-tab ${activeModule === "weight" ? "is-active" : ""}`}
          onClick={() => selectModule("weight")}
          role="tab"
          type="button"
        >
          <img alt="" className="module-tab-icon" src={asset("tab_weight.png")} />
          体重
        </button>
        <button
          aria-selected={activeModule === "food"}
          className={`module-tab ${activeModule === "food" ? "is-active" : ""}`}
          onClick={() => selectModule("food")}
          role="tab"
          type="button"
        >
          <img alt="" className="module-tab-icon" src={asset("tab_food.png")} />
          饮食
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
              <button className="upload-zone" onClick={openPhotoPicker} type="button">
                <img alt="" src={asset("food_camera.png")} />
                <span>{photoName || "点击上传食物照片"}</span>
              </button>
              <input accept="image/*" className="sr-only" onChange={handlePhotoChange} ref={photoInputRef} type="file" />
            </label>
            {uploadFeedback ? <p className="interaction-note" role="status">{uploadFeedback}</p> : null}
            <div className="form-grid">
              <label className="field wide">
                <span>食物</span>
                <select className="select" defaultValue="manual">
                  <option value="manual">-- 手动输入 --</option>
                </select>
              </label>
              <label className="field wide">
                <span className="sr-only">食物名称</span>
                <input className="input" onChange={(event) => setFood(event.currentTarget.value)} placeholder="输入食物名称" value={food} />
              </label>
              <label className="field">
                <span>热量(千卡)</span>
                <input className="input" inputMode="numeric" onChange={(event) => setCalories(event.currentTarget.value)} value={calories} />
              </label>
              <label className="field">
                <span>餐次</span>
                <select className="select" onChange={(event) => setMeal(event.currentTarget.value)} value={meal}>
                  <option>早餐</option>
                  <option>午餐</option>
                  <option>晚餐</option>
                  <option>加餐</option>
                </select>
              </label>
              <label className="field">
                <span>日期</span>
                <input className="input" onChange={(event) => setDate(event.currentTarget.value)} readOnly={reference} value={date} />
              </label>
              <label className="field">
                <span>备注</span>
                <input className="input" onChange={(event) => setNote(event.currentTarget.value)} placeholder="可选" value={note} />
              </label>
            </div>
            <button className="primary full" onClick={addFoodRecord} type="button">
              ＋ 记录饮食
            </button>
          </>
        ) : (
          <div className="empty module-empty" aria-live="polite">
            <p>{activeModule === "exercise" ? "选择运动项目后即可在登录状态下同步记录。" : "填写体重后即可在登录状态下同步记录。"}</p>
          </div>
        )}
        {moduleFeedback ? <p className="interaction-note" role="status">{moduleFeedback}</p> : null}
      </form>
      <article className="total-card" aria-live="polite">
        <span>今日摄入总热量</span>
        <b>{totalCalories}</b>
        <span>千卡</span>
      </article>
      {foodRecords.length > 0 ? (
        <section className="card record-list-card" aria-live="polite">
          <h2 className="section-title">本次饮食记录</h2>
          <ul className="record-items">
            {foodRecords.map((record) => (
              <li className="record-item" key={record.id}>
                <div>
                  <strong>{record.food}</strong>
                  <p>{record.meal} · {record.calories} 千卡</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

export function PeriodClient({ reference }: { reference: boolean }) {
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [feedback, setFeedback] = useState("");
  const [records, setRecords] = useState<string[]>([]);

  function addPeriodRecord() {
    const start = startDate.trim();
    const end = endDate.trim();
    if (!start) {
      setFeedback("请先填写开始日期，再记录经期。");
      return;
    }
    const summary = end ? `${start} 至 ${end}` : `${start} 开始`;
    setRecords((current) => [summary, ...current]);
    setFeedback("经期记录已保存到当前会话；登录后可同步到工作台。");
    setStartDate("");
    setEndDate("");
  }

  return (
    <>
      <form className="card period-form" onSubmit={(event) => event.preventDefault()}>
        <div className="form-grid">
          <label className="field">
            <span>开始日期</span>
            <input className="input" onChange={(event) => setStartDate(event.currentTarget.value)} readOnly={reference} value={startDate} />
          </label>
          <label className="field">
            <span>结束日期</span>
            <input className="input" onChange={(event) => setEndDate(event.currentTarget.value)} readOnly={reference} value={endDate} />
          </label>
        </div>
        <button className="primary full" onClick={addPeriodRecord} type="button">
          ＋ 记录经期
        </button>
      </form>
      <article className="card period-overview">
        <h2 className="section-title">
          <img alt="" src={asset("period_title.png")} />
          周期概览
        </h2>
        <div className="period-stats">
          <div className="period-stat">
            <span>当前周期</span>
            <b>--</b>
          </div>
          <div className="period-stat">
            <span>预测下次（估算）</span>
            <b>--</b>
          </div>
          <div className="period-stat">
            <span>平均周期</span>
            <b>--</b>
          </div>
        </div>
      </article>
      <article className="card period-history" aria-live="polite">
        <h2 className="section-title">
          <span aria-hidden="true" className="section-glyph">
            ≡
          </span>
          历史记录
        </h2>
        {feedback ? <p className="interaction-note" role="status">{feedback}</p> : null}
        {records.length === 0 ? (
          <div className="empty">
            <p>还没有经期记录</p>
          </div>
        ) : (
          <ul className="record-items">
            {records.map((record, index) => (
              <li className="record-item" key={`${record}-${index}`}>
                <strong>{record}</strong>
              </li>
            ))}
          </ul>
        )}
      </article>
    </>
  );
}

export function GenericPageClient({ label }: { label: string }) {
  const [records, setRecords] = useState<string[]>([]);
  const [feedback, setFeedback] = useState("");

  function addRecord() {
    const nextNumber = records.length + 1;
    setRecords((current) => [`第 ${nextNumber} 条${label}记录`, ...current]);
    setFeedback("已新增到当前会话；登录后可同步到工作台。");
  }

  return (
    <article className="card generic-card" aria-live="polite">
      <p className="muted">把今天真正要完成的小事，温柔地放在这里。</p>
      <button className="primary full" onClick={addRecord} type="button">
        ＋ 新增记录
      </button>
      {feedback ? <p className="interaction-note" role="status">{feedback}</p> : null}
      {records.length > 0 ? (
        <ul className="record-items">
          {records.map((record) => (
            <li className="record-item" key={record}>
              <strong>{record}</strong>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}
