"use client";

import { FormEvent, useState, useSyncExternalStore } from "react";
import { isDeviceLocalRecord } from "./local-record-cache";
import {
  asBoolean,
  asText,
  ResourceStatus,
  TenantRecord,
  todayIsoDate,
  useTenantResource,
} from "./tenant-resource-client";

type TodoRecord = TenantRecord & {
  completed?: boolean | number;
  completed_at?: number | null;
  due_date?: string | null;
  note?: string;
  priority?: string;
  title?: string;
};

function nonEmpty(value: string): string {
  return value.trim();
}

function savedOnDevice(record: TodoRecord): boolean {
  return isDeviceLocalRecord(record);
}

function useInteractionReady(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}

/**
 * Todos use the shared tenant resource client so the page has the same
 * account-scoped device cache, verified-session writes, retry queue and
 * account-switch protection as every other workbench module.
 */
export default function TodoPageClient() {
  const todos = useTenantResource<TodoRecord>("todos");
  const interactionReady = useInteractionReady();
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [dueDate, setDueDate] = useState(() => todayIsoDate());
  const [priority, setPriority] = useState("normal");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState("待办会先保存在当前设备；登录后可自动同步。");

  function clearForm() {
    setEditingId(null);
    setTitle("");
    setNote("");
    setDueDate(todayIsoDate());
    setPriority("normal");
  }

  function startEditing(todo: TodoRecord) {
    setEditingId(todo.id);
    setTitle(asText(todo.title));
    setNote(asText(todo.note));
    setDueDate(asText(todo.due_date, todayIsoDate()));
    setPriority(asText(todo.priority, "normal"));
    setMessage("正在编辑这条待办；修改后点击保存修改。");
  }

  function cancelEditing() {
    clearForm();
    setMessage("已取消修改，可以继续新增待办。");
  }

  async function submitTodo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedTitle = nonEmpty(title);
    if (!normalizedTitle) {
      setMessage("标题不能为空。");
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dueDate)) {
      setMessage("请按 YYYY-MM-DD 填写截止日期。");
      return;
    }

    const payload = {
      dueDate,
      note: nonEmpty(note),
      priority,
      title: normalizedTitle,
    };
    const wasEditing = Boolean(editingId);
    const saved = editingId
      ? await todos.update(editingId, payload)
      : await todos.create({ ...payload, completed: false, completedAt: null });
    if (!saved) return;

    clearForm();
    if (savedOnDevice(saved)) {
      setMessage(wasEditing ? "待办已在当前设备修改。" : "待办已保存在当前设备。连接恢复后会自动同步。");
    } else {
      setMessage(wasEditing ? "待办已修改，历史列表已更新。" : "待办已保存，历史列表已更新。");
    }
  }

  async function toggleTodo(todo: TodoRecord) {
    const completing = !asBoolean(todo.completed);
    const saved = await todos.update(todo.id, completing
      ? { completed: true }
      : { completed: false, completedAt: null });
    if (!saved) return;
    if (savedOnDevice(saved)) {
      setMessage(completing ? "待办已在当前设备标记完成。" : "待办已在当前设备恢复为待完成。");
    } else {
      setMessage(completing ? "待办已完成，历史列表已更新。" : "待办已恢复为待完成。");
    }
  }

  async function deleteTodo(todo: TodoRecord) {
    const deleted = await todos.destroy(todo.id);
    if (!deleted) return;
    if (editingId === todo.id) clearForm();
    setMessage(savedOnDevice(todo) ? "已删除当前设备的待办。" : "待办已删除，历史列表已更新。");
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
        <ResourceStatus
          authRequired={todos.authRequired}
          consentRequired={todos.consentRequired}
          error={todos.error}
          loading={todos.loading}
          loginSuggested={todos.loginSuggested}
        />
        {message ? <p className="account-note">{message}</p> : null}
        {!todos.loading && !todos.error && todos.records.length === 0 ? (
          <div className="empty">
            <p>还没有待办，先来一条吧～</p>
          </div>
        ) : null}
        <ul className="record-items">
          {todos.records.map((todo) => {
            const completed = asBoolean(todo.completed);
            return (
              <li className="record-item" key={todo.id}>
                <div>
                  <strong>{todo.title}</strong>
                  <p>{todo.note || "（无备注）"}</p>
                </div>
                <div className="record-meta">
                  <small>{todo.due_date ?? "未设置截止日"}</small>
                  <small>{todo.priority ?? "normal"}</small>
                  <small>{completed ? "已完成" : "待完成"}</small>
                  <button className="record-remove" disabled={todos.saving} onClick={() => void toggleTodo(todo)} type="button">
                    {completed ? "恢复" : "完成"}
                  </button>
                  <button className="record-remove" disabled={todos.saving} onClick={() => startEditing(todo)} type="button">
                    编辑
                  </button>
                  <button className="record-remove" disabled={todos.saving} onClick={() => void deleteTodo(todo)} type="button">
                    删除
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="card todo-form">
        <h2 className="section-title">{editingId ? "编辑待办" : "新增待办"}</h2>
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
          <button className="primary full" disabled={!interactionReady || todos.saving} type="submit">
            {todos.saving ? "保存中…" : editingId ? "保存修改" : "＋ 新增待办"}
          </button>
        </form>
        {editingId ? <button className="auth-secondary-link" onClick={cancelEditing} type="button">取消修改</button> : null}
      </section>

      <button
        className="auth-secondary-link"
        type="button"
        onClick={() => {
          setMessage("正在刷新待办历史…");
          void todos.reload();
        }}
      >
        刷新待办
      </button>
    </>
  );
}
