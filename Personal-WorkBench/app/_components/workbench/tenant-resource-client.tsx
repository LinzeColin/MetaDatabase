"use client";

import { useCallback, useEffect, useState } from "react";

export type TenantRecord = Record<string, unknown> & {
  id: string;
};

type ApiEnvelope<T extends TenantRecord> = {
  data?: T | T[];
};

export type ResourceState<T extends TenantRecord> = {
  authRequired: boolean;
  consentRequired: boolean;
  loginSuggested: boolean;
  create: (payload: Record<string, unknown>, idempotencyKey?: string) => Promise<T | null>;
  destroy: (id: string, idempotencyKey?: string) => Promise<boolean>;
  error: string;
  loading: boolean;
  records: T[];
  reload: () => Promise<void>;
  saving: boolean;
};

type ResourceOptions = {
  enabled?: boolean;
  sensitive?: boolean;
};

function newIdempotencyKey(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isRecord(value: unknown): value is TenantRecord {
  return Boolean(value) && typeof value === "object" && typeof (value as { id?: unknown }).id === "string";
}

function failureMessage(status: number, sensitive: boolean): {
  authRequired: boolean;
  consentRequired: boolean;
  message: string;
} {
  if (status === 401) {
    return { authRequired: true, consentRequired: false, message: "请先登录并完成邮箱验证，再保存和查看你的历史记录。" };
  }
  if (status === 403 && sensitive) {
    return {
      authRequired: false,
      consentRequired: true,
      message: "这类记录需要你先在账户页明确开启敏感内容跨设备保存。",
    };
  }
  if (status === 403) {
    return { authRequired: true, consentRequired: false, message: "请先完成邮箱验证后继续。" };
  }
  if (status === 409) {
    return { authRequired: false, consentRequired: false, message: "这条记录已发生变化，已保留现有数据，请刷新后再试。" };
  }
  if (status >= 500) {
    return { authRequired: false, consentRequired: false, message: "服务暂时不可用，请稍后再试。" };
  }
  return { authRequired: false, consentRequired: false, message: "保存失败，请检查填写内容后重试。" };
}

async function readEnvelope<T extends TenantRecord>(response: Response): Promise<ApiEnvelope<T>> {
  try {
    const value = (await response.json()) as unknown;
    return value && typeof value === "object" ? (value as ApiEnvelope<T>) : {};
  } catch {
    return {};
  }
}

export function todayIsoDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function asText(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

export function asBoolean(value: unknown, fallback = false): boolean {
  return value === true || value === 1 ? true : value === false || value === 0 ? false : fallback;
}

export function yuanToCents(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  const cents = Math.round(parsed * 100);
  return Number.isSafeInteger(cents) && cents > 0 ? cents : null;
}

export function centsToYuan(value: unknown): string {
  return `¥${(asNumber(value) / 100).toFixed(2)}`;
}

export function localDateTimeToTimestamp(value: string): number | null {
  if (!value) return null;
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}

export function timestampToLocalDate(value: unknown): string {
  const timestamp = asNumber(value, Number.NaN);
  if (!Number.isFinite(timestamp)) return "未设置时间";
  return new Date(timestamp).toLocaleString("zh-CN", { hour12: false });
}

/**
 * All product records use the same session-first API. The server derives the
 * tenant from the verified session, so this client never sends an owner/user
 * identifier or stores cross-account data in browser state.
 */
export function useTenantResource<T extends TenantRecord>(
  resource: string,
  { enabled = true, sensitive = false }: ResourceOptions = {},
): ResourceState<T> {
  const [records, setRecords] = useState<T[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [authRequired, setAuthRequired] = useState(false);
  const [consentRequired, setConsentRequired] = useState(false);
  const [loginSuggested, setLoginSuggested] = useState(false);

  const applyFailure = useCallback((status: number) => {
    const failure = failureMessage(status, sensitive);
    setError(failure.message);
    setAuthRequired(failure.authRequired);
    setConsentRequired(failure.consentRequired);
    setLoginSuggested(failure.authRequired);
  }, [sensitive]);

  const reload = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    try {
      const response = await fetch(`/api/mydairy/${resource}`, { credentials: "same-origin" });
      if (!response.ok) {
        setRecords([]);
        applyFailure(response.status);
        return;
      }
      const payload = await readEnvelope<T>(response);
      setRecords(Array.isArray(payload.data) ? payload.data.filter(isRecord) : []);
      setError("");
      setAuthRequired(false);
      setConsentRequired(false);
      setLoginSuggested(false);
    } catch {
      setError("暂时无法读取你的历史记录。请先登录并完成邮箱验证；若已登录，请检查网络后重试。");
      setLoginSuggested(true);
    } finally {
      setLoading(false);
    }
  }, [applyFailure, enabled, resource]);

  useEffect(() => {
    // The initial request is the external-system synchronization for this resource.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload]);

  const create = useCallback(async (payload: Record<string, unknown>, idempotencyKey?: string): Promise<T | null> => {
    if (!enabled) return null;
    setSaving(true);
    setError("");
    setLoginSuggested(false);
    try {
      const response = await fetch(`/api/mydairy/${resource}`, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "idempotency-key": idempotencyKey ?? newIdempotencyKey(resource),
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        applyFailure(response.status);
        return null;
      }
      const data = (await readEnvelope<T>(response)).data;
      if (!isRecord(data)) {
        setError("保存结果不完整，请刷新后确认历史记录。");
        return null;
      }
      setRecords((current) => [data, ...current.filter((record) => record.id !== data.id)]);
      setAuthRequired(false);
      setConsentRequired(false);
      setLoginSuggested(false);
      return data;
    } catch {
      setError("暂时无法保存这条记录。请先登录并完成邮箱验证；若已登录，请检查网络后重试。");
      setLoginSuggested(true);
      return null;
    } finally {
      setSaving(false);
    }
  }, [applyFailure, enabled, resource]);

  const destroy = useCallback(async (id: string, idempotencyKey?: string): Promise<boolean> => {
    if (!enabled || !id) return false;
    setSaving(true);
    setError("");
    setLoginSuggested(false);
    try {
      const response = await fetch(`/api/mydairy/${resource}/${encodeURIComponent(id)}`, {
        method: "DELETE",
        credentials: "same-origin",
        headers: { "idempotency-key": idempotencyKey ?? newIdempotencyKey(`${resource}-delete`) },
      });
      if (!response.ok) {
        applyFailure(response.status);
        return false;
      }
      setRecords((current) => current.filter((record) => record.id !== id));
      setLoginSuggested(false);
      return true;
    } catch {
      setError("暂时无法删除这条记录。请先登录并完成邮箱验证；若已登录，请检查网络后重试。");
      setLoginSuggested(true);
      return false;
    } finally {
      setSaving(false);
    }
  }, [applyFailure, enabled, resource]);

  return { authRequired, consentRequired, create, destroy, error, loading, loginSuggested, records, reload, saving };
}

export function ResourceStatus({
  authRequired,
  consentRequired,
  error,
  loginSuggested,
  loading,
}: Pick<ResourceState<TenantRecord>, "authRequired" | "consentRequired" | "error" | "loading" | "loginSuggested">) {
  if (loading) return <p className="interaction-note" role="status">正在读取你的历史记录…</p>;
  if (!error) return null;
  return (
    <p className="interaction-note" role="status">
      {error}{" "}
      {authRequired || loginSuggested ? <a className="data-link" href="/auth/sign-in">去登录</a> : null}
      {consentRequired ? <a className="data-link" href="/account">前往账户设置</a> : null}
    </p>
  );
}
