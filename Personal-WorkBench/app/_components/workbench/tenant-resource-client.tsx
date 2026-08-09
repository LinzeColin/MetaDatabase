"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createDeviceLocalRecord,
  isDeviceLocalRecord,
  mergeWithDeviceLocalRecords,
  readDeviceLocalRecords,
  removeDeviceLocalRecord,
  resolveBrowserRecordScope,
  writeDeviceLocalRecord,
} from "./local-record-cache";

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

type CloudAvailability = "available" | "consent_required" | "unavailable" | "unknown" | "unauthorized";

function newIdempotencyKey(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function withRequestId(path: string, idempotencyKey: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}request_id=${encodeURIComponent(idempotencyKey)}`;
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

function cloudAvailabilityFor(status: number, sensitive: boolean): CloudAvailability {
  if (status === 401) return "unauthorized";
  if (status === 403 && sensitive) return "consent_required";
  return "unavailable";
}

function localSaveMessage(availability: CloudAvailability, sensitive: boolean): string {
  if (availability === "unauthorized") {
    return "已保存在当前设备。登录并完成邮箱验证后，后续记录可跨设备同步。";
  }
  if (availability === "consent_required") {
    return "已保存在当前设备。本条未上传；如需后续敏感记录跨设备同步，请在账户页明确开启。";
  }
  if (sensitive) {
    return "已保存在当前设备。本条未上传；待登录并确认跨设备保存后，可继续同步新的敏感记录。";
  }
  return "已保存在当前设备。服务恢复后可重新保存以同步到其他设备。";
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
 * identifier. Device-only fallback records are partitioned by an opaque
 * account scope and never auto-migrate across an account boundary.
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
  const [scopeReady, setScopeReady] = useState(!enabled);
  const recordsRef = useRef<T[]>([]);
  const localRecordsRef = useRef<T[]>([]);
  const scopeRef = useRef<string | null>(null);
  const scopeInitializationRef = useRef<Promise<void> | null>(null);
  const cloudAvailabilityRef = useRef<CloudAvailability>("unknown");

  const commitRecords = useCallback((next: T[]) => {
    recordsRef.current = next;
    setRecords(next);
  }, []);

  const commitLocalRecords = useCallback((next: T[]) => {
    localRecordsRef.current = next;
  }, []);

  const applyFailure = useCallback((status: number) => {
    const failure = failureMessage(status, sensitive);
    setError(failure.message);
    setAuthRequired(failure.authRequired);
    setConsentRequired(failure.consentRequired);
    setLoginSuggested(failure.authRequired);
  }, [sensitive]);

  const acknowledgeLocalSave = useCallback((availability: CloudAvailability) => {
    setError(localSaveMessage(availability, sensitive));
    setAuthRequired(availability === "unauthorized");
    setConsentRequired(availability === "consent_required");
    setLoginSuggested(availability === "unauthorized");
  }, [sensitive]);

  useEffect(() => {
    let cancelled = false;
    const initializeScope = async () => {
      // Defer state synchronization to the asynchronous browser-storage path.
      await Promise.resolve();
      if (cancelled) return;
      scopeRef.current = null;
      cloudAvailabilityRef.current = "unknown";
      commitRecords([]);
      commitLocalRecords([]);
      setScopeReady(!enabled);
      if (!enabled) {
        setLoading(false);
        return;
      }
      setLoading(true);
      const scope = await resolveBrowserRecordScope();
      let local: T[] = [];
      try {
        local = (await readDeviceLocalRecords(scope, resource)) as T[];
      } catch {
        // The server path remains available if a browser disables IndexedDB.
      }
      if (cancelled) return;
      scopeRef.current = scope;
      commitLocalRecords(local);
      commitRecords(local);
      setScopeReady(true);
    };
    const initialization = initializeScope();
    scopeInitializationRef.current = initialization;
    void initialization;

    return () => {
      cancelled = true;
    };
  }, [commitLocalRecords, commitRecords, enabled, resource]);

  const reload = useCallback(async () => {
    if (!enabled || !scopeRef.current) return;
    setLoading(true);
    try {
      const response = await fetch(`/api/mydairy/${resource}`, { credentials: "same-origin" });
      if (!response.ok) {
        cloudAvailabilityRef.current = cloudAvailabilityFor(response.status, sensitive);
        commitRecords(localRecordsRef.current);
        applyFailure(response.status);
        return;
      }
      const payload = await readEnvelope<T>(response);
      const remote = Array.isArray(payload.data) ? payload.data.filter(isRecord) : [];
      cloudAvailabilityRef.current = "available";
      commitRecords(mergeWithDeviceLocalRecords(remote, localRecordsRef.current));
      setError("");
      setAuthRequired(false);
      setConsentRequired(false);
      setLoginSuggested(false);
    } catch {
      cloudAvailabilityRef.current = "unavailable";
      commitRecords(localRecordsRef.current);
      setError("暂时无法读取你的历史记录。请先登录并完成邮箱验证；若已登录，请检查网络后重试。");
      setLoginSuggested(true);
    } finally {
      setLoading(false);
    }
  }, [applyFailure, commitRecords, enabled, resource, sensitive]);

  useEffect(() => {
    if (!scopeReady) return;
    // The initial request is the external-system synchronization for this resource.
    void reload();
  }, [reload, scopeReady]);

  const create = useCallback(async (payload: Record<string, unknown>, idempotencyKey?: string): Promise<T | null> => {
    if (!enabled) return null;
    if (!scopeRef.current && scopeInitializationRef.current) await scopeInitializationRef.current;
    if (!scopeRef.current) return null;
    setSaving(true);
    setError("");
    setLoginSuggested(false);
    const requestId = idempotencyKey ?? newIdempotencyKey(resource);
    const deviceLocalRecord = createDeviceLocalRecord(payload);
    const localRecord = deviceLocalRecord as T;
    let localPersisted = false;
    try {
      await writeDeviceLocalRecord(scopeRef.current, resource, deviceLocalRecord);
      localPersisted = true;
      const nextLocal = [localRecord, ...localRecordsRef.current.filter((record) => record.id !== localRecord.id)];
      commitLocalRecords(nextLocal);
      commitRecords([localRecord, ...recordsRef.current.filter((record) => record.id !== localRecord.id)]);
    } catch {
      // Do not report a local save when the device cannot actually retain it.
    }

    // Sensitive records must stay on-device until the verified session has
    // positively confirmed the user's cross-device consent.
    if (sensitive && cloudAvailabilityRef.current !== "available") {
      if (localPersisted) {
        acknowledgeLocalSave(cloudAvailabilityRef.current);
        setSaving(false);
        return localRecord;
      }
      setError("当前设备无法保存这条敏感记录，请检查浏览器存储权限后重试。");
      setSaving(false);
      return null;
    }

    try {
      const response = await fetch(withRequestId(`/api/mydairy/${resource}`, requestId), {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        cloudAvailabilityRef.current = cloudAvailabilityFor(response.status, sensitive);
        if (localPersisted) {
          acknowledgeLocalSave(cloudAvailabilityRef.current);
          return localRecord;
        }
        applyFailure(response.status);
        return null;
      }
      const data = (await readEnvelope<T>(response)).data;
      if (!isRecord(data)) {
        cloudAvailabilityRef.current = "unavailable";
        if (localPersisted) {
          acknowledgeLocalSave("unavailable");
          return localRecord;
        }
        setError("保存结果不完整，请刷新后确认历史记录。");
        return null;
      }
      cloudAvailabilityRef.current = "available";
      if (localPersisted && scopeRef.current) {
        try {
          await removeDeviceLocalRecord(scopeRef.current, resource, localRecord.id);
        } catch {
          // A stale local duplicate stays private to this device and can be removed later.
        }
      }
      const nextLocal = localRecordsRef.current.filter((record) => record.id !== localRecord.id);
      commitLocalRecords(nextLocal);
      commitRecords([data, ...recordsRef.current.filter((record) => record.id !== data.id && record.id !== localRecord.id)]);
      setAuthRequired(false);
      setConsentRequired(false);
      setLoginSuggested(false);
      return data;
    } catch {
      cloudAvailabilityRef.current = "unavailable";
      if (localPersisted) {
        acknowledgeLocalSave("unavailable");
        return localRecord;
      }
      setError("暂时无法保存这条记录。请先登录并完成邮箱验证；若已登录，请检查网络后重试。");
      setLoginSuggested(true);
      return null;
    } finally {
      setSaving(false);
    }
  }, [acknowledgeLocalSave, applyFailure, commitLocalRecords, commitRecords, enabled, resource, sensitive]);

  const destroy = useCallback(async (id: string, idempotencyKey?: string): Promise<boolean> => {
    if (!enabled || !id) return false;
    if (!scopeRef.current && scopeInitializationRef.current) await scopeInitializationRef.current;
    if (!scopeRef.current) return false;
    setSaving(true);
    setError("");
    setLoginSuggested(false);
    const local = localRecordsRef.current.find((record) => record.id === id);
    if (local && isDeviceLocalRecord(local)) {
      try {
        await removeDeviceLocalRecord(scopeRef.current, resource, id);
        const nextLocal = localRecordsRef.current.filter((record) => record.id !== id);
        commitLocalRecords(nextLocal);
        commitRecords(recordsRef.current.filter((record) => record.id !== id));
        return true;
      } catch {
        setError("当前设备无法删除这条本机记录，请检查浏览器存储权限后重试。");
        return false;
      } finally {
        setSaving(false);
      }
    }
    try {
      const requestId = idempotencyKey ?? newIdempotencyKey(`${resource}-delete`);
      const response = await fetch(withRequestId(`/api/mydairy/${resource}/${encodeURIComponent(id)}`, requestId), {
        method: "DELETE",
        credentials: "same-origin",
      });
      if (!response.ok) {
        applyFailure(response.status);
        return false;
      }
      commitRecords(recordsRef.current.filter((record) => record.id !== id));
      setLoginSuggested(false);
      return true;
    } catch {
      setError("暂时无法删除这条记录。请先登录并完成邮箱验证；若已登录，请检查网络后重试。");
      setLoginSuggested(true);
      return false;
    } finally {
      setSaving(false);
    }
  }, [applyFailure, commitLocalRecords, commitRecords, enabled, resource]);

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
