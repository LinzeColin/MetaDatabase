"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  appendOutbox,
  getBrowserOutboxStorage,
  OutboxAction,
  OutboxMutationResult,
  readOutbox,
  replayOutboxQueue,
  writeOutbox,
} from "./outbox-queue";
import { withRequestId } from "./tenant-resource-client";


type TodoRecord = {
  id: string;
  title: string;
  note: string;
  due_date: string | null;
  priority: string;
  completed: number;
  completed_at: number | null;
  created_at: number;
  updated_at: number;
};

function toChineseDate(fallback = ""): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(fallback)) return fallback;
  const today = new Date();
  const m = String(today.getMonth() + 1).padStart(2, "0");
  const d = String(today.getDate()).padStart(2, "0");
  return `${today.getFullYear()}-${m}-${d}`;
}

function safeString(value: string, fallback = "") {
  const text = value.trim();
  return text.length ? text : fallback;
}

export default function TodoPageClient() {
  const [todos, setTodos] = useState<TodoRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [priority, setPriority] = useState("normal");
  const [message, setMessage] = useState("登录后可同步记录");
  const [outboxCount, setOutboxCount] = useState(0);
  const [replayedBanner, setReplayedBanner] = useState("");
  const outboxStorage = useMemo(() => getBrowserOutboxStorage(), []);

  const loadTodos = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/mydairy/todos", {
        credentials: "same-origin",
      });
      if (!response.ok) {
        setTodos([]);
        if (response.status === 401) {
          setError("请先登录后继续。");
          return;
        }
        throw new Error("读取待办失败");
      }
      const payload = (await response.json()) as { data?: TodoRecord[] };
      const rows = Array.isArray(payload.data) ? payload.data : [];
      const sorted = [...rows].sort((a, b) => b.updated_at - a.updated_at);
      setTodos(sorted);
      setError("");
    } catch {
      setError("当前网络不可用，请稍后重试。");
    } finally {
      setLoading(false);
      setOutboxCount(readOutbox(outboxStorage).length);
    }
  }, [outboxStorage]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadTodos();
  }, [loadTodos]);

  const queueCountFromStorage = useCallback(() => {
    const count = readOutbox(outboxStorage).length;
    setOutboxCount(count);
    return count;
  }, [outboxStorage]);

  const sendMutation = useCallback(async (
    action: OutboxAction,
    options: { quiet?: boolean } = {},
  ): Promise<OutboxMutationResult> => {
    const response = await fetch(withRequestId(action.endpoint, action.idempotencyKey), {
      method: action.method,
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(action.payload),
    });

    const payload = (await response.json().catch(() => null)) as { data?: TodoRecord; replayed?: boolean; message?: string };
    if (!response.ok) {
      if (response.status === 409) {
        return { type: "conflict" as const, message: safeString(payload?.message ?? "操作与历史写入不一致") };
      }
      if (response.status === 503) {
        return { type: "unavailable" as const, message: "服务暂时不可用，请稍后再试。" };
      }
      return { type: "error" as const, message: safeString(payload?.message ?? "操作失败") };
    }

    if (payload?.replayed) {
      setReplayedBanner("该操作已成功去重（之前已提交过同一请求）。");
      setTimeout(() => setReplayedBanner(""), 2200);
    }
    if (!options.quiet && payload?.data) {
      const data = payload.data;
      setTodos((prev) => [data, ...prev.filter((row) => row.id !== data.id)].sort((a, b) => b.updated_at - a.updated_at));
    }
    return { type: "ok" as const };
  }, []);

  const flushOutbox = useCallback(async () => {
    if (typeof navigator !== "undefined" && !navigator.onLine) return;
    const queue = readOutbox(outboxStorage);
    if (!queue.length) {
      queueCountFromStorage();
      return;
    }
    const replayResult = await replayOutboxQueue(queue, (action) => sendMutation(action, { quiet: true }));
    if (replayResult.stopType === "conflict") {
      setError(replayResult.stopMessage ?? "操作与历史写入不一致");
    }
    if (replayResult.stopType === "error") {
      setError(replayResult.stopMessage ?? "操作失败");
    }
    if (replayResult.stopType === "unavailable") {
      setMessage(replayResult.stopMessage ?? "服务暂时不可用，请稍后再试。");
    }
    if (replayResult.stopType === "network") {
      setError("网络异常，暂未能重放出站记录。");
    }
    writeOutbox(outboxStorage, replayResult.remaining);
    queueCountFromStorage();
    if (replayResult.replayedAny) void loadTodos();
  }, [loadTodos, outboxStorage, queueCountFromStorage, sendMutation]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void flushOutbox();
    if (typeof window === "undefined") return;
    const syncOutbox = () => {
      void flushOutbox();
    };
    window.addEventListener("online", syncOutbox);
    return () => {
      window.removeEventListener("online", syncOutbox);
    };
  }, [flushOutbox]);

  async function enqueueOrSend(action: OutboxAction) {
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      appendOutbox(outboxStorage, action);
      queueCountFromStorage();
      setMessage("当前处于离线状态，已加入本地待发队列。恢复网络后自动重放。");
      return;
    }

    try {
      const result = await sendMutation(action);
      if (result.type === "ok") {
        await loadTodos();
        return;
      }
      if (result.type === "unavailable") {
        appendOutbox(outboxStorage, action);
        queueCountFromStorage();
        setMessage("服务暂时不可用，已暂存为离线重放记录。");
        return;
      }
      setError(result.message ?? "操作失败");
    } catch {
      appendOutbox(outboxStorage, action);
      queueCountFromStorage();
      setMessage("网络异常，已加入待发队列，恢复网络后自动重放。");
    }
  }

  async function submitTodo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const normalizedTitle = safeString(title, "");
    if (!normalizedTitle) {
      setError("标题不能为空。");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    const action: OutboxAction = {
      endpoint: "/api/mydairy/todos",
      method: "POST",
      idempotencyKey: crypto.randomUUID(),
      createdAt: Date.now(),
      queuedAt: Date.now(),
      payload: {
        title: normalizedTitle,
        note: safeString(note),
        dueDate: safeString(dueDate, toChineseDate("")),
        priority,
      },
    };

    await enqueueOrSend(action);
    setTitle("");
    setNote("");
    setDueDate("");
    setPriority("normal");
    setBusy(false);
  }

  return (
    <>
      <section className="card record-list-card" aria-live="polite">
        <h2 className="section-title">
          <span aria-hidden="true" className="section-glyph">
            ≡
          </span>
          待办列表
        </h2>
        {loading ? <p className="muted">正在同步…</p> : null}
        {replayedBanner ? <p className="account-note">{replayedBanner}</p> : null}
        {outboxCount > 0 ? <p className="account-note">本地待发队列：{outboxCount} 条</p> : null}
        {error ? <p className="auth-message" role="alert">{error}</p> : null}
        {message ? <p className="account-note">{message}</p> : null}
        {todos.length === 0 ? (
          <div className="empty">
            <p>还没有待办，先来一条吧～</p>
          </div>
        ) : null}
        <ul className="record-items">
          {todos.map((todo) => (
            <li className="record-item" key={todo.id}>
              <div>
                <strong>{todo.title}</strong>
                <p>{todo.note || "（无备注）"}</p>
              </div>
              <div className="record-meta">
                <small>{todo.due_date ?? "未设置截止日"}</small>
                <small>{todo.priority}</small>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="card todo-form">
        <h2 className="section-title">新增待办</h2>
        <form className="field-form" onSubmit={submitTodo}>
          <div className="form-grid">
            <label className="field">
              <span>标题</span>
              <input
                className="input"
                required
                maxLength={300}
                value={title}
                onChange={(event) => setTitle(event.currentTarget.value)}
              />
            </label>
            <label className="field wide">
              <span>截止日期</span>
              <input
                className="input"
                placeholder="YYYY-MM-DD"
                value={dueDate}
                onChange={(event) => setDueDate(event.currentTarget.value)}
                required
                pattern="\\d{4}-\\d{2}-\\d{2}"
              />
            </label>
            <label className="field">
              <span>优先级</span>
              <select
                className="select"
                value={priority}
                onChange={(event) => setPriority(event.currentTarget.value)}
              >
                <option value="low">低</option>
                <option value="normal">中</option>
                <option value="high">高</option>
              </select>
            </label>
            <label className="field wide">
              <span>备注</span>
              <input
                className="input"
                value={note}
                onChange={(event) => setNote(event.currentTarget.value)}
                maxLength={5000}
              />
            </label>
          </div>
          <button className="primary full" disabled={busy} type="submit">
            {busy ? "提交中…" : "＋ 新增待办"}
          </button>
        </form>
      </section>

      <button
        className="auth-secondary-link"
        type="button"
        onClick={() => {
          setMessage("正在手动同步中…");
          void loadTodos();
        }}
      >
        刷新待办
      </button>
    </>
  );
}
