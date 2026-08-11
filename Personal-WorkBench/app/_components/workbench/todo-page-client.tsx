"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  appendDeviceOutbox,
  createDeviceLocalRecord,
  DeviceLocalRecord,
  DeviceOutboxAction,
  isDeviceLocalRecord,
  mergeWithDeviceLocalRecords,
  readDeviceLocalRecords,
  readDeviceOutbox,
  removeDeviceOutboxActions,
  removeDeviceLocalRecord,
  resolveBrowserRecordScope,
  writeDeviceLocalRecord,
  writeDeviceOutbox,
} from "./local-record-cache";
import {
  getBrowserOutboxStorage,
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

type CachedTodoRecord = TodoRecord & DeviceLocalRecord;

type TodoMutationResult = {
  data?: TodoRecord;
  message?: string;
  type: "conflict" | "error" | "ok" | "unavailable";
};

const TODO_RESOURCE = "todos";

function actionTargetsTodo(action: DeviceOutboxAction): boolean {
  return action.method === "POST" && action.endpoint === "/api/mydairy/todos";
}

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

function sortTodos(rows: TodoRecord[]): TodoRecord[] {
  return [...rows].sort((left, right) => right.updated_at - left.updated_at);
}

function isCachedTodoRecord(value: unknown): value is CachedTodoRecord {
  return isDeviceLocalRecord(value)
    && typeof value.title === "string"
    && typeof value.note === "string"
    && (typeof value.due_date === "string" || value.due_date === null)
    && typeof value.priority === "string"
    && typeof value.completed === "number"
    && (typeof value.completed_at === "number" || value.completed_at === null);
}

function dedupeActions(actions: DeviceOutboxAction[]): DeviceOutboxAction[] {
  const seen = new Set<string>();
  return actions.filter((action) => {
    if (seen.has(action.idempotencyKey)) return false;
    seen.add(action.idempotencyKey);
    return true;
  });
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `todo-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * The normal page keeps the frozen visual tree, but its persistence plane is
 * now IndexedDB-first. A queued action always points at the local row it will
 * replace after the server confirms the same idempotency key.
 */
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
  const [scopeReady, setScopeReady] = useState(false);
  const legacyOutboxStorage = useMemo(() => getBrowserOutboxStorage(), []);
  const scopeRef = useRef<string | null>(null);
  const localTodosRef = useRef<TodoRecord[]>([]);
  const todosRef = useRef<TodoRecord[]>([]);

  const commitTodos = useCallback((next: TodoRecord[]) => {
    const sorted = sortTodos(next);
    todosRef.current = sorted;
    setTodos(sorted);
  }, []);

  const commitLocalTodos = useCallback((next: TodoRecord[]) => {
    localTodosRef.current = sortTodos(next);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const initializeScope = async () => {
      scopeRef.current = null;
      localTodosRef.current = [];
      todosRef.current = [];
      setScopeReady(false);
      setLoading(true);
      const scope = await resolveBrowserRecordScope();
      let local: TodoRecord[] = [];
      let actions: DeviceOutboxAction[] = [];
      try {
        local = (await readDeviceLocalRecords(scope, TODO_RESOURCE)).filter(isCachedTodoRecord);
        actions = await readDeviceOutbox(scope);
        // Previous releases used one global localStorage key. Its ownership is
        // unknowable after an account switch, so migrate it only into the safe
        // guest partition; it never auto-replays as a signed-in account.
        if (scope === "guest") {
          const legacy = readOutbox(legacyOutboxStorage) as DeviceOutboxAction[];
          if (legacy.length) {
            actions = dedupeActions([...actions, ...legacy]);
            await writeDeviceOutbox(scope, actions);
            writeOutbox(legacyOutboxStorage, []);
          }
        }
      } catch {
        // A server-backed session can still work when browser storage is disabled.
      }
      if (cancelled) return;
      scopeRef.current = scope;
      commitLocalTodos(local);
      commitTodos(local);
      setOutboxCount(actions.length);
      setScopeReady(true);
    };
    void initializeScope();
    return () => {
      cancelled = true;
    };
  }, [commitLocalTodos, commitTodos, legacyOutboxStorage]);

  const loadTodos = useCallback(async () => {
    const scope = scopeRef.current;
    if (!scopeReady || !scope) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/mydairy/todos", { credentials: "same-origin" });
      if (!response.ok) {
        commitTodos(localTodosRef.current);
        setError(response.status === 401
          ? "请先登录后继续。本机待办仍保留在当前设备。"
          : "暂时无法读取云端历史；本机待办仍保留在当前设备。");
        return;
      }
      const payload = (await response.json()) as { data?: TodoRecord[] };
      const remote = Array.isArray(payload.data) ? payload.data : [];
      commitTodos(mergeWithDeviceLocalRecords(remote, localTodosRef.current));
      setError("");
    } catch {
      commitTodos(localTodosRef.current);
      setError("当前网络不可用；本机待办仍保留在当前设备。");
    } finally {
      setLoading(false);
      try {
        setOutboxCount((await readDeviceOutbox(scope)).length);
      } catch {
        // The visible local rows remain truthful even if the queue count cannot load.
      }
    }
  }, [commitTodos, scopeReady]);

  const commitRemoteTodo = useCallback(async (action: DeviceOutboxAction, data: TodoRecord) => {
    const scope = scopeRef.current;
    const localRecordId = action.localRecordId;
    if (scope && localRecordId) {
      try {
        await removeDeviceLocalRecord(scope, TODO_RESOURCE, localRecordId);
      } catch {
        // A private duplicate may remain in IDB, never crosses the account boundary,
        // and is retained rather than risking loss before the next reconciliation.
      }
    }
    const nextLocal = localRecordId
      ? localTodosRef.current.filter((item) => item.id !== localRecordId)
      : localTodosRef.current;
    commitLocalTodos(nextLocal);
    commitTodos([data, ...todosRef.current.filter((item) => item.id !== data.id && item.id !== localRecordId)]);
  }, [commitLocalTodos, commitTodos]);

  const sendMutation = useCallback(async (action: DeviceOutboxAction): Promise<TodoMutationResult> => {
    const response = await fetch(withRequestId(action.endpoint, action.idempotencyKey), {
      method: action.method,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(action.payload),
    });
    const payload = (await response.json().catch(() => null)) as { data?: TodoRecord; replayed?: boolean; message?: string } | null;
    if (!response.ok) {
      if (response.status === 409) {
        return { type: "conflict", message: safeString(payload?.message ?? "操作与历史写入不一致") };
      }
      if (response.status === 503) return { type: "unavailable", message: "服务暂时不可用，请稍后再试。" };
      return { type: "error", message: safeString(payload?.message ?? "操作失败") };
    }
    if (!payload?.data) return { type: "error", message: "保存结果不完整，请稍后重试。" };
    if (payload.replayed) {
      setReplayedBanner("该操作已成功去重（之前已提交过同一请求）。");
      setTimeout(() => setReplayedBanner(""), 2200);
    }
    return { type: "ok", data: payload.data };
  }, []);

  const flushOutbox = useCallback(async () => {
    const scope = scopeRef.current;
    if (!scope || !scopeReady || (typeof navigator !== "undefined" && !navigator.onLine)) return;
    let allActions: DeviceOutboxAction[];
    try {
      allActions = await readDeviceOutbox(scope);
    } catch {
      return;
    }
    const queue = allActions.filter(actionTargetsTodo);
    if (!queue.length) {
      setOutboxCount(allActions.length);
      return;
    }
    const replayResult = await replayOutboxQueue(queue, async (action) => {
      const result = await sendMutation(action);
      if (result.type === "ok" && result.data) await commitRemoteTodo(action, result.data);
      return result;
    });
    try {
      const remaining = new Set(replayResult.remaining.map((action) => action.idempotencyKey));
      const acknowledged = queue
        .filter((action) => !remaining.has(action.idempotencyKey))
        .map((action) => action.idempotencyKey);
      if (acknowledged.length) await removeDeviceOutboxActions(scope, acknowledged);
      setOutboxCount((await readDeviceOutbox(scope)).length);
    } catch {
      setError("本机待发队列暂时无法更新；待办历史仍保留在当前设备。");
      return;
    }
    if (replayResult.replayedAny) setMessage("已同步本机待办记录。");
    if (replayResult.stopType === "conflict" || replayResult.stopType === "error") {
      setError(replayResult.stopMessage ?? "操作与历史写入不一致");
    }
    if (replayResult.stopType === "unavailable") {
      setMessage(replayResult.stopMessage ?? "服务暂时不可用，待办仍保存在当前设备。");
    }
    if (replayResult.stopType === "network") {
      setMessage("网络异常，待办仍保存在当前设备，恢复网络后会继续同步。");
    }
  }, [commitRemoteTodo, scopeReady, sendMutation]);

  useEffect(() => {
    if (!scopeReady) return;
    void loadTodos();
    void flushOutbox();
  }, [flushOutbox, loadTodos, scopeReady]);

  useEffect(() => {
    if (!scopeReady || typeof window === "undefined") return;
    const syncOutbox = () => void flushOutbox();
    window.addEventListener("online", syncOutbox);
    return () => window.removeEventListener("online", syncOutbox);
  }, [flushOutbox, scopeReady]);

  const queueAction = useCallback(async (action: DeviceOutboxAction, messageText: string) => {
    const scope = scopeRef.current;
    if (!scope) return false;
    try {
      const next = await appendDeviceOutbox(scope, action);
      setOutboxCount(next.length);
      setMessage(messageText);
      return true;
    } catch {
      setError("待办已保存在当前设备，但本机待发队列暂时不可用，请恢复网络后手动同步。");
      return false;
    }
  }, []);

  const enqueueOrSend = useCallback(async (action: DeviceOutboxAction) => {
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      await queueAction(action, "待办已保存在当前设备；恢复网络后会自动同步。");
      return;
    }
    try {
      const result = await sendMutation(action);
      if (result.type === "ok" && result.data) {
        await commitRemoteTodo(action, result.data);
        setMessage("待办已保存并同步。");
        return;
      }
      if (result.type === "unavailable") {
        await queueAction(action, "服务暂时不可用，待办已保存在当前设备，将在恢复后同步。");
        return;
      }
      if (result.type === "conflict") {
        setError(result.message ?? "操作与历史写入不一致");
        return;
      }
      setMessage("待办已保存在当前设备。登录并完成邮箱验证后，可继续同步到其他设备。");
      setError(result.message ?? "云端暂未接受本条记录。");
    } catch {
      await queueAction(action, "网络异常，待办已保存在当前设备，恢复网络后会自动同步。");
    }
  }, [commitRemoteTodo, queueAction, sendMutation]);

  async function submitTodo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const normalizedTitle = safeString(title, "");
    if (!normalizedTitle) {
      setError("标题不能为空。");
      return;
    }
    const scope = scopeRef.current;
    if (!scopeReady || !scope) {
      setError("正在初始化当前设备的待办存储，请稍后再试。");
      return;
    }

    const now = Date.now();
    const payload = {
      dueDate: safeString(dueDate, toChineseDate("")),
      note: safeString(note),
      priority,
      title: normalizedTitle,
    };
    const localTodo = createDeviceLocalRecord({
      ...payload,
      completed: 0,
      completedAt: null,
    }, now) as TodoRecord & DeviceLocalRecord;
    const action: DeviceOutboxAction = {
      createdAt: now,
      endpoint: "/api/mydairy/todos",
      idempotencyKey: newIdempotencyKey(),
      localRecordId: localTodo.id,
      method: "POST",
      payload,
      queuedAt: now,
    };

    setBusy(true);
    setError("");
    setMessage("");
    try {
      await writeDeviceLocalRecord(scope, TODO_RESOURCE, localTodo);
      const nextLocal = [localTodo, ...localTodosRef.current.filter((item) => item.id !== localTodo.id)];
      commitLocalTodos(nextLocal);
      commitTodos([localTodo, ...todosRef.current.filter((item) => item.id !== localTodo.id)]);
      await enqueueOrSend(action);
      setTitle("");
      setNote("");
      setDueDate("");
      setPriority("normal");
    } catch {
      setError("当前设备无法保存待办，请检查浏览器存储权限后重试。");
    } finally {
      setBusy(false);
    }
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
        {outboxCount > 0 ? <p className="account-note">本机待发队列：{outboxCount} 条</p> : null}
        {error ? <p className="auth-message" role="alert">{error}</p> : null}
        {message ? <p className="account-note">{message}</p> : null}
        {!loading && !error && todos.length === 0 ? (
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
                pattern="[0-9]{4}-[0-9]{2}-[0-9]{2}"
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
          void flushOutbox();
        }}
      >
        刷新待办
      </button>
    </>
  );
}
