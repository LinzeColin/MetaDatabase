"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  appendDeviceOutbox,
  createDeviceLocalRecord,
  deriveDeviceOutboxParentReferences,
  type DeviceLocalRecord,
  DeviceOutboxAction,
  isDeviceLocalRecord,
  mergeWithDeviceLocalRecords,
  rememberDeviceOutboxRecordAlias,
  readDeviceLocalRecords,
  readDeviceOutbox,
  removeDeviceOutboxActions,
  removeDeviceLocalRecord,
  resolveDeviceOutboxAction,
  resolveBrowserRecordScope,
  writeDeviceLocalRecord,
} from "./local-record-cache";
import { replayOutboxQueue, type OutboxMutationResult } from "./outbox-queue";

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
  update: (id: string, payload: Record<string, unknown>, idempotencyKey?: string) => Promise<T | null>;
};

type ResourceOptions = {
  enabled?: boolean;
  sensitive?: boolean;
};

type ApiFailureCode = "EMAIL_VERIFICATION_REQUIRED" | "SENSITIVE_CLOUD_CONSENT_REQUIRED";
type CloudAvailability =
  | "available"
  | "consent_required"
  | "unavailable"
  | "unknown"
  | "unauthorized"
  | "verification_required";

function actionTargetsResource(action: DeviceOutboxAction, resource: string): boolean {
  return action.method === "POST" && action.endpoint === `/api/mydairy/${resource}`;
}

function shouldQueueForReplay(status: number, sensitive: boolean): boolean {
  if (sensitive) return false;
  return status === 401 || status === 403 || status >= 500;
}

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

function failureMessage(status: number, sensitive: boolean, code: ApiFailureCode | null = null): {
  authRequired: boolean;
  consentRequired: boolean;
  message: string;
} {
  if (code === "SENSITIVE_CLOUD_CONSENT_REQUIRED") {
    return {
      authRequired: false,
      consentRequired: true,
      message: "这类记录需要你先在账户页明确开启敏感内容跨设备保存。",
    };
  }
  if (code === "EMAIL_VERIFICATION_REQUIRED") {
    return {
      authRequired: true,
      consentRequired: false,
      message: "当前账号尚未完成保存验证。若刚使用 Google 登录，请退出后重新登录；邮箱账号请完成验证邮件。",
    };
  }
  if (status === 401) {
    return {
      authRequired: true,
      consentRequired: false,
      message: "请先登录后再保存和查看你的历史记录。使用 Google 登录无需额外验证邮箱。",
    };
  }
  if (status === 403) {
    return {
      authRequired: true,
      consentRequired: false,
      message: sensitive
        ? "当前会话尚未满足敏感记录保存条件。请刷新后确认登录状态和跨设备保存设置。"
        : "当前会话尚未满足保存条件。请刷新后重新登录再试。",
    };
  }
  if (status === 409) {
    return { authRequired: false, consentRequired: false, message: "这条记录已发生变化，已保留现有数据，请刷新后再试。" };
  }
  if (status >= 500) {
    return { authRequired: false, consentRequired: false, message: "服务暂时不可用，请稍后再试。" };
  }
  return { authRequired: false, consentRequired: false, message: "保存失败，请检查填写内容后重试。" };
}

function cloudAvailabilityFor(status: number, code: ApiFailureCode | null): CloudAvailability {
  if (status === 401) return "unauthorized";
  if (code === "SENSITIVE_CLOUD_CONSENT_REQUIRED") return "consent_required";
  if (code === "EMAIL_VERIFICATION_REQUIRED") return "verification_required";
  return "unavailable";
}

function localSaveMessage(availability: CloudAvailability, sensitive: boolean, queuedForReplay = false): string {
  if (availability === "verification_required") {
    return queuedForReplay
      ? "已保存在当前设备。当前账号尚未完成保存验证；验证状态更新后会继续同步。"
      : "已保存在当前设备。当前账号尚未完成保存验证；若刚使用 Google 登录，请退出后重新登录，邮箱账号请完成验证邮件。";
  }
  if (queuedForReplay && availability === "unauthorized") {
    return "已保存在当前设备。完成登录后会自动同步；使用 Google 登录无需额外验证邮箱。";
  }
  if (queuedForReplay) {
    return "已保存在当前设备。连接恢复后会自动同步。";
  }
  if (availability === "unauthorized") {
    return "已保存在当前设备。登录后可跨设备同步；使用 Google 登录无需额外验证邮箱。";
  }
  if (availability === "consent_required") {
    return "已保存在当前设备。本条未上传；如需后续敏感记录跨设备同步，请在账户页明确开启。";
  }
  if (sensitive) {
    return "已保存在当前设备。本条暂未上传；请刷新后确认登录状态和跨设备保存设置。";
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

async function readFailureCode(response: Response): Promise<ApiFailureCode | null> {
  try {
    const value = await response.json() as { code?: unknown };
    if (value.code === "EMAIL_VERIFICATION_REQUIRED" || value.code === "SENSITIVE_CLOUD_CONSENT_REQUIRED") {
      return value.code;
    }
  } catch {
    // A malformed failure payload must not change the conservative fallback.
  }
  return null;
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
  const scopeRefreshRef = useRef<Promise<string | null> | null>(null);
  const cloudAvailabilityRef = useRef<CloudAvailability>("unknown");

  const commitRecords = useCallback((next: T[]) => {
    recordsRef.current = next;
    setRecords(next);
  }, []);

  const commitLocalRecords = useCallback((next: T[]) => {
    localRecordsRef.current = next;
  }, []);

  const applyFailure = useCallback((status: number, code: ApiFailureCode | null = null) => {
    const failure = failureMessage(status, sensitive, code);
    setError(failure.message);
    setAuthRequired(failure.authRequired);
    setConsentRequired(failure.consentRequired);
    setLoginSuggested(failure.authRequired);
  }, [sensitive]);

  /**
   * A session may change in another tab while this view remains mounted. Never
   * merge an old account's device-only rows with the newly authenticated
   * account's remote history: reload the opaque partition before each remote
   * operation instead.
   */
  const refreshCurrentScope = useCallback(async (): Promise<string | null> => {
    if (!enabled) return null;
    if (scopeRefreshRef.current) return scopeRefreshRef.current;
    const refresh = (async () => {
      let nextScope = "guest";
      try {
        nextScope = await resolveBrowserRecordScope();
      } catch {
        // Treat an unavailable session lookup as the isolated guest partition.
      }
      if (nextScope === scopeRef.current) return nextScope;

      scopeRef.current = null;
      cloudAvailabilityRef.current = "unknown";
      commitRecords([]);
      commitLocalRecords([]);
      let local: T[] = [];
      try {
        local = (await readDeviceLocalRecords(nextScope, resource)) as T[];
      } catch {
        // The remote path remains available if browser storage is unavailable.
      }
      scopeRef.current = nextScope;
      commitLocalRecords(local);
      commitRecords(local);
      return nextScope;
    })();
    scopeRefreshRef.current = refresh;
    try {
      return await refresh;
    } finally {
      if (scopeRefreshRef.current === refresh) scopeRefreshRef.current = null;
    }
  }, [commitLocalRecords, commitRecords, enabled, resource]);

  const acknowledgeScopeChange = useCallback((scope: string | null) => {
    const signedOut = scope === "guest";
    setError(signedOut
      ? "登录状态已改变。原账户的本机记录已隔离，请登录后刷新历史记录。"
      : "账户已切换。原账户的本机记录已隔离，请刷新后继续。",
    );
    setAuthRequired(signedOut);
    setConsentRequired(false);
    setLoginSuggested(signedOut);
  }, []);

  const acknowledgeLocalSave = useCallback((availability: CloudAvailability, queuedForReplay = false) => {
    const needsSignIn = availability === "unauthorized" || availability === "verification_required";
    setError(localSaveMessage(availability, sensitive, queuedForReplay));
    setAuthRequired(needsSignIn);
    setConsentRequired(availability === "consent_required");
    setLoginSuggested(needsSignIn);
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

  const queueDeviceMutation = useCallback(async (action: DeviceOutboxAction): Promise<boolean> => {
    const scope = scopeRef.current;
    // A guest browser has no verified owner. Its local records intentionally
    // stay device-only rather than being replayed under a later account.
    if (!scope || scope === "guest") return false;
    try {
      await appendDeviceOutbox(scope, action);
      return true;
    } catch {
      return false;
    }
  }, []);

  const flushDeviceOutbox = useCallback(async (remote: T[], expectedScope: string): Promise<T[]> => {
    const scope = scopeRef.current;
    // Sensitive records require a current explicit consent path; this generic
    // replay never treats a previously local sensitive row as consented.
    if (!scope || scope !== expectedScope || scope === "guest" || sensitive) return remote;
    let actions: DeviceOutboxAction[];
    try {
      actions = (await readDeviceOutbox(scope)).filter((action) => actionTargetsResource(action, resource));
    } catch {
      return remote;
    }
    if (!actions.length) return remote;

    let reconciled = remote;
    const replayResult = await replayOutboxQueue(actions, async (action): Promise<OutboxMutationResult> => {
      try {
        const resolvedAction = await resolveDeviceOutboxAction(scope, action);
        if (!resolvedAction) {
          return { type: "unavailable", message: "正在等待关联记录同步，本机记录仍会保留。" };
        }
        const scopeBeforeReplay = await refreshCurrentScope();
        if (scopeBeforeReplay !== expectedScope) {
          return { type: "error", message: "账户已切换，本机待发记录仍保留在原账户分区。" };
        }
        const response = await fetch(withRequestId(resolvedAction.endpoint, resolvedAction.idempotencyKey), {
          method: resolvedAction.method,
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(resolvedAction.payload),
        });
        const scopeAfterReplay = await refreshCurrentScope();
        if (scopeAfterReplay !== expectedScope) {
          return { type: "error", message: "账户已切换，本机待发记录仍保留在原账户分区。" };
        }
        if (!response.ok) {
          const code = await readFailureCode(response);
          if (response.status === 409) return { type: "conflict", message: failureMessage(response.status, false).message };
          if (response.status >= 500) return { type: "unavailable", message: "服务暂时不可用，请稍后再试。" };
          return { type: "error", message: failureMessage(response.status, false, code).message };
        }
        const data = (await readEnvelope<T>(response)).data;
        if (!isRecord(data)) return { type: "error", message: "保存结果不完整，请刷新后确认历史记录。" };

        await rememberDeviceOutboxRecordAlias(scope, action, data.id);

        if (action.localRecordId) {
          try {
            await removeDeviceLocalRecord(scope, resource, action.localRecordId);
          } catch {
            // Preserve the idempotent action until the local row can be
            // reconciled. Retrying cannot cross the account boundary.
            return { type: "unavailable", message: "本机记录暂时无法完成同步。" };
          }
        }
        const nextLocal = action.localRecordId
          ? localRecordsRef.current.filter((record) => record.id !== action.localRecordId)
          : localRecordsRef.current;
        commitLocalRecords(nextLocal);
        reconciled = [data, ...reconciled.filter((record) => record.id !== data.id && record.id !== action.localRecordId)];
        return { type: "ok" };
      } catch {
        return { type: "unavailable", message: "网络异常，记录仍保存在当前设备。" };
      }
    });

    const remaining = new Set(replayResult.remaining.map((action) => action.idempotencyKey));
    const acknowledged = actions
      .filter((action) => !remaining.has(action.idempotencyKey))
      .map((action) => action.idempotencyKey);
    if (acknowledged.length) {
      try {
        await removeDeviceOutboxActions(scope, acknowledged);
      } catch {
        // Retain safe idempotent retries if browser storage cannot acknowledge
        // the queue cleanup in this pass.
      }
    }
    return reconciled;
  }, [commitLocalRecords, refreshCurrentScope, resource, sensitive]);

  const reload = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    let requestScope: string | null = null;
    try {
      requestScope = await refreshCurrentScope();
      if (!requestScope) return;
      const response = await fetch(`/api/mydairy/${resource}`, { credentials: "same-origin" });
      const responseScope = await refreshCurrentScope();
      if (responseScope !== requestScope) {
        acknowledgeScopeChange(responseScope);
        return;
      }
      if (!response.ok) {
        const code = await readFailureCode(response);
        cloudAvailabilityRef.current = cloudAvailabilityFor(response.status, code);
        commitRecords(localRecordsRef.current);
        applyFailure(response.status, code);
        return;
      }
      const payload = await readEnvelope<T>(response);
      const remote = Array.isArray(payload.data) ? payload.data.filter(isRecord) : [];
      cloudAvailabilityRef.current = "available";
      const reconciled = await flushDeviceOutbox(remote, requestScope);
      const reconciledScope = await refreshCurrentScope();
      if (reconciledScope !== requestScope) {
        acknowledgeScopeChange(reconciledScope);
        return;
      }
      commitRecords(mergeWithDeviceLocalRecords(reconciled, localRecordsRef.current));
      setError("");
      setAuthRequired(false);
      setConsentRequired(false);
      setLoginSuggested(false);
    } catch {
      const failureScope = await refreshCurrentScope();
      if (requestScope && failureScope !== requestScope) {
        acknowledgeScopeChange(failureScope);
        return;
      }
      cloudAvailabilityRef.current = "unavailable";
      commitRecords(localRecordsRef.current);
      setError("暂时无法读取你的历史记录。请先确认已登录；使用 Google 登录无需额外验证邮箱。若已登录，请检查网络后重试。");
      setLoginSuggested(true);
    } finally {
      setLoading(false);
    }
  }, [acknowledgeScopeChange, applyFailure, commitRecords, enabled, flushDeviceOutbox, refreshCurrentScope, resource, sensitive]);

  useEffect(() => {
    if (!scopeReady) return;
    let cancelled = false;
    // Schedule the initial external-system synchronization after this render so
    // an account-scope refresh cannot cascade another synchronous effect render.
    const timer = window.setTimeout(() => {
      if (!cancelled) void reload();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [reload, scopeReady]);

  useEffect(() => {
    if (!enabled || !scopeReady || typeof window === "undefined") return;
    const replayWhenOnline = () => void reload();
    const refreshWhenVisible = () => void reload();
    const refreshWhenDocumentVisible = () => {
      if (typeof document !== "undefined" && document.visibilityState === "visible") void reload();
    };
    const replayWhenParentSynchronizes = () => void reload();
    window.addEventListener("online", replayWhenOnline);
    window.addEventListener("focus", refreshWhenVisible);
    window.addEventListener("mydairy:outbox-alias-resolved", replayWhenParentSynchronizes);
    if (typeof document !== "undefined") document.addEventListener("visibilitychange", refreshWhenDocumentVisible);
    return () => {
      window.removeEventListener("online", replayWhenOnline);
      window.removeEventListener("focus", refreshWhenVisible);
      window.removeEventListener("mydairy:outbox-alias-resolved", replayWhenParentSynchronizes);
      if (typeof document !== "undefined") document.removeEventListener("visibilitychange", refreshWhenDocumentVisible);
    };
  }, [enabled, reload, scopeReady]);

  const create = useCallback(async (payload: Record<string, unknown>, idempotencyKey?: string): Promise<T | null> => {
    if (!enabled) return null;
    if (!scopeRef.current && scopeInitializationRef.current) await scopeInitializationRef.current;
    const scope = await refreshCurrentScope();
    if (!scope) return null;
    setSaving(true);
    setError("");
    setLoginSuggested(false);

    // A signed-in user can submit before the initial resource GET settles.
    // For sensitive modules, resolve the existing read-only consent gate first
    // instead of prematurely classifying that window as device-only. The
    // server still rejects any non-consented cloud path before body parsing.
    if (sensitive && cloudAvailabilityRef.current === "unknown") {
      await reload();
      const preflightScope = await refreshCurrentScope();
      if (preflightScope !== scope) {
        acknowledgeScopeChange(preflightScope);
        setSaving(false);
        return null;
      }
    }

    const requestId = idempotencyKey ?? newIdempotencyKey(resource);
    const deviceLocalRecord = createDeviceLocalRecord(payload);
    const localRecord = deviceLocalRecord as T;
    let localPersisted = false;
    try {
      await writeDeviceLocalRecord(scope, resource, deviceLocalRecord);
      localPersisted = true;
      const nextLocal = [localRecord, ...localRecordsRef.current.filter((record) => record.id !== localRecord.id)];
      commitLocalRecords(nextLocal);
      commitRecords([localRecord, ...recordsRef.current.filter((record) => record.id !== localRecord.id)]);
    } catch {
      // Do not report a local save when the device cannot actually retain it.
    }
    const parentReferences = deriveDeviceOutboxParentReferences(resource, payload);
    const deviceOutboxAction: DeviceOutboxAction = {
      createdAt: deviceLocalRecord.created_at,
      endpoint: `/api/mydairy/${resource}`,
      idempotencyKey: requestId,
      localRecordId: deviceLocalRecord.id,
      method: "POST",
      ...(parentReferences.length ? { parentReferences } : {}),
      payload,
      queuedAt: deviceLocalRecord.created_at,
    };

    const scopeBeforeRequest = await refreshCurrentScope();
    if (scopeBeforeRequest !== scope) {
      acknowledgeScopeChange(scopeBeforeRequest);
      setSaving(false);
      return null;
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
      const resolvedAction = await resolveDeviceOutboxAction(scope, deviceOutboxAction);
      if (!resolvedAction) {
        if (localPersisted) {
          const queuedForReplay = sensitive ? false : await queueDeviceMutation(deviceOutboxAction);
          setError(queuedForReplay
            ? "已保存在当前设备。正在等待关联记录同步，完成后会自动同步。"
            : "已保存在当前设备。关联记录正在同步，请稍后刷新后再试。",
          );
          setAuthRequired(false);
          setConsentRequired(false);
          setLoginSuggested(false);
          return localRecord;
        }
        setError("关联记录正在同步，请稍后刷新后再试。");
        return null;
      }
      const resolvedScope = await refreshCurrentScope();
      if (resolvedScope !== scope) {
        acknowledgeScopeChange(resolvedScope);
        return null;
      }
      const response = await fetch(withRequestId(resolvedAction.endpoint, requestId), {
        method: resolvedAction.method,
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(resolvedAction.payload),
      });
      const responseScope = await refreshCurrentScope();
      if (responseScope !== scope) {
        acknowledgeScopeChange(responseScope);
        return null;
      }
      if (!response.ok) {
        const code = await readFailureCode(response);
        cloudAvailabilityRef.current = cloudAvailabilityFor(response.status, code);
        if (localPersisted) {
          const queuedForReplay = shouldQueueForReplay(response.status, sensitive)
            ? await queueDeviceMutation(deviceOutboxAction)
            : false;
          acknowledgeLocalSave(cloudAvailabilityRef.current, queuedForReplay);
          return localRecord;
        }
        applyFailure(response.status, code);
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
      await rememberDeviceOutboxRecordAlias(scope, deviceOutboxAction, data.id);
      if (localPersisted) {
        try {
          await removeDeviceLocalRecord(scope, resource, localRecord.id);
        } catch {
          // A stale local duplicate stays private to this device and can be removed later.
        }
      }
      try {
        await removeDeviceOutboxActions(scope, [requestId]);
      } catch {
        // A stale idempotent retry remains account-scoped and is safe to
        // reconcile on the next successful resource read.
      }
      const nextLocal = localRecordsRef.current.filter((record) => record.id !== localRecord.id);
      commitLocalRecords(nextLocal);
      commitRecords([data, ...recordsRef.current.filter((record) => record.id !== data.id && record.id !== localRecord.id)]);
      setAuthRequired(false);
      setConsentRequired(false);
      setLoginSuggested(false);
      return data;
    } catch {
      const failureScope = await refreshCurrentScope();
      if (failureScope !== scope) {
        acknowledgeScopeChange(failureScope);
        return null;
      }
      cloudAvailabilityRef.current = "unavailable";
      if (localPersisted) {
        const queuedForReplay = sensitive ? false : await queueDeviceMutation(deviceOutboxAction);
        acknowledgeLocalSave("unavailable", queuedForReplay);
        return localRecord;
      }
      setError("暂时无法保存这条记录。请先确认已登录；使用 Google 登录无需额外验证邮箱。若已登录，请检查网络后重试。");
      setLoginSuggested(true);
      return null;
    } finally {
      setSaving(false);
    }
  }, [acknowledgeLocalSave, acknowledgeScopeChange, applyFailure, commitLocalRecords, commitRecords, enabled, queueDeviceMutation, refreshCurrentScope, reload, resource, sensitive]);

  /**
   * Update keeps the same two-plane rule as create: a device-local row may be
   * corrected immediately on this device, while an existing cloud row is
   * patched only through the verified session-derived tenant route. Local
   * corrections are intentionally not replayed as a new account's mutation.
   */
  const update = useCallback(async (id: string, payload: Record<string, unknown>, idempotencyKey?: string): Promise<T | null> => {
    if (!enabled || !id) return null;
    if (!scopeRef.current && scopeInitializationRef.current) await scopeInitializationRef.current;
    const scope = await refreshCurrentScope();
    if (!scope) return null;
    setSaving(true);
    setError("");
    setLoginSuggested(false);

    const local = localRecordsRef.current.find((record) => record.id === id);
    if (local && isDeviceLocalRecord(local)) {
      const patch = createDeviceLocalRecord(payload, Date.now(), id);
      const updatedLocal = {
        ...local,
        ...patch,
        created_at: typeof local.created_at === "number" ? local.created_at : patch.created_at,
      } as T & DeviceLocalRecord;
      try {
        await writeDeviceLocalRecord(scope, resource, updatedLocal);
        const nextLocal = localRecordsRef.current.map((record) => record.id === id ? updatedLocal : record);
        commitLocalRecords(nextLocal);
        commitRecords(recordsRef.current.map((record) => record.id === id ? updatedLocal : record));
        return updatedLocal;
      } catch {
        setError("当前设备无法更新这条本机记录，请检查浏览器存储权限后重试。");
        return null;
      } finally {
        setSaving(false);
      }
    }

    // For a sensitive cloud record, confirm the existing read-only consent
    // state first. A missing consent never sends a PATCH body to the server.
    if (sensitive && cloudAvailabilityRef.current === "unknown") {
      await reload();
      const preflightScope = await refreshCurrentScope();
      if (preflightScope !== scope) {
        acknowledgeScopeChange(preflightScope);
        setSaving(false);
        return null;
      }
    }
    if (sensitive && cloudAvailabilityRef.current !== "available") {
      if (cloudAvailabilityRef.current === "consent_required") {
        setError("这类记录需要你先在账户页明确开启敏感内容跨设备保存。");
        setConsentRequired(true);
      } else {
        setError("暂时无法确认当前账号的跨设备保存状态，请刷新后再试。");
        setLoginSuggested(true);
      }
      setSaving(false);
      return null;
    }

    try {
      const requestId = idempotencyKey ?? newIdempotencyKey(`${resource}-update`);
      const response = await fetch(withRequestId(`/api/mydairy/${resource}/${encodeURIComponent(id)}`, requestId), {
        method: "PATCH",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const responseScope = await refreshCurrentScope();
      if (responseScope !== scope) {
        acknowledgeScopeChange(responseScope);
        return null;
      }
      if (!response.ok) {
        const code = await readFailureCode(response);
        cloudAvailabilityRef.current = cloudAvailabilityFor(response.status, code);
        applyFailure(response.status, code);
        return null;
      }
      const data = (await readEnvelope<T>(response)).data;
      if (!isRecord(data)) {
        setError("保存结果不完整，请刷新后确认历史记录。");
        return null;
      }
      cloudAvailabilityRef.current = "available";
      commitRecords(recordsRef.current.map((record) => record.id === id ? data : record));
      setAuthRequired(false);
      setConsentRequired(false);
      setLoginSuggested(false);
      return data;
    } catch {
      const failureScope = await refreshCurrentScope();
      if (failureScope !== scope) {
        acknowledgeScopeChange(failureScope);
        return null;
      }
      setError("暂时无法更新这条记录。请先确认已登录；使用 Google 登录无需额外验证邮箱。若已登录，请检查网络后重试。");
      setLoginSuggested(true);
      return null;
    } finally {
      setSaving(false);
    }
  }, [acknowledgeScopeChange, applyFailure, commitLocalRecords, commitRecords, enabled, refreshCurrentScope, reload, resource, sensitive]);

  const destroy = useCallback(async (id: string, idempotencyKey?: string): Promise<boolean> => {
    if (!enabled || !id) return false;
    if (!scopeRef.current && scopeInitializationRef.current) await scopeInitializationRef.current;
    const scope = await refreshCurrentScope();
    if (!scope) return false;
    setSaving(true);
    setError("");
    setLoginSuggested(false);
    const local = localRecordsRef.current.find((record) => record.id === id);
    if (local && isDeviceLocalRecord(local)) {
      try {
        await removeDeviceLocalRecord(scope, resource, id);
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
      const responseScope = await refreshCurrentScope();
      if (responseScope !== scope) {
        acknowledgeScopeChange(responseScope);
        return false;
      }
      if (!response.ok) {
        applyFailure(response.status, await readFailureCode(response));
        return false;
      }
      commitRecords(recordsRef.current.filter((record) => record.id !== id));
      setLoginSuggested(false);
      return true;
    } catch {
      const failureScope = await refreshCurrentScope();
      if (failureScope !== scope) {
        acknowledgeScopeChange(failureScope);
        return false;
      }
      setError("暂时无法删除这条记录。请先确认已登录；使用 Google 登录无需额外验证邮箱。若已登录，请检查网络后重试。");
      setLoginSuggested(true);
      return false;
    } finally {
      setSaving(false);
    }
  }, [acknowledgeScopeChange, applyFailure, commitLocalRecords, commitRecords, enabled, refreshCurrentScope, resource]);

  return { authRequired, consentRequired, create, destroy, error, loading, loginSuggested, records, reload, saving, update };
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
      {consentRequired ? <a className="data-link" href="/account">开启敏感跨设备保存</a> : null}
    </p>
  );
}
