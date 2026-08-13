"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  buildGuestDeviceHistoryEnvelope,
  type GuestDeviceHistoryEnvelope,
} from "../_components/workbench/local-record-cache";
import { requestWithTimeout } from "../_components/workbench/request-timeout";

type ImportPreview = {
  canApply?: boolean;
  counts?: Record<string, number>;
  duplicateIds?: string[];
  invalidItems?: Array<unknown>;
};

type ImportResult = {
  state?: "previewed" | "applying" | "completed" | "failed";
  preview?: ImportPreview;
  replayed?: boolean;
  totalInserted?: number;
};

type DeviceHistoryTransferPanelProps = {
  previewOnArrival?: boolean;
  returnTo?: string | null;
};

const sensitiveModules = new Set(["ledger", "weight", "diary", "period"]);

function newRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `guest-device-history-${crypto.randomUUID()}`;
  }
  return `guest-device-history-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isImportResult(value: unknown): value is ImportResult {
  return isRecord(value) && (!value.preview || isRecord(value.preview));
}

function totalCount(envelope: GuestDeviceHistoryEnvelope | null): number {
  if (!envelope) return 0;
  return Object.values(envelope.modules).reduce((total, rows) => total + (Array.isArray(rows) ? rows.length : 0), 0);
}

function containsSensitiveHistory(envelope: GuestDeviceHistoryEnvelope | null): boolean {
  if (!envelope) return false;
  return Object.entries(envelope.modules).some(([module, rows]) => sensitiveModules.has(module) && Array.isArray(rows) && rows.length > 0);
}

function previewCount(preview: ImportPreview | null): number {
  if (!preview?.counts) return 0;
  return Object.values(preview.counts).reduce((total, count) => total + (Number.isFinite(count) ? count : 0), 0);
}

function failureMessage(status: number): string {
  if (status === 401) return "登录状态已失效，请重新登录后再试。";
  if (status === 403) return "这台设备的记录含敏感内容；请先在上方核对当前跨设备同步设置。";
  if (status === 409) return "预览发现重复或无效记录，未导入任何内容。";
  if (status >= 500) return "迁移服务暂时不可用；这台设备上的原记录没有改变，可稍后重试。";
  return "无法处理这台设备的记录；原记录没有改变。";
}

/**
 * Guest records are intentionally never promoted automatically after login.
 * This is the sole, preview-first escape hatch for the same person who used a
 * device before creating an account. It cannot read another account scope and
 * it never deletes the device source after import.
 */
export function DeviceHistoryTransferPanel({ previewOnArrival = false, returnTo }: DeviceHistoryTransferPanelProps) {
  const [envelope, setEnvelope] = useState<GuestDeviceHistoryEnvelope | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [requestId, setRequestId] = useState("");
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState("正在检查这台设备上是否有登录前保存的记录…");
  const autoPreviewConsumed = useRef(false);

  const inspectDeviceHistory = async () => {
    setBusy(true);
    setPreview(null);
    try {
      const nextEnvelope = await buildGuestDeviceHistoryEnvelope();
      const count = totalCount(nextEnvelope);
      setEnvelope(nextEnvelope);
      setRequestId(count ? newRequestId() : "");
      setMessage(count
        ? `发现这台设备上有 ${count} 条登录前记录。先预览，再由你确认导入到当前账号。`
        : "这台设备上没有发现可导入的登录前记录。",
      );
    } catch {
      setEnvelope(null);
      setRequestId("");
      setMessage("暂时无法读取这台设备的本机记录；没有修改任何记录。可稍后重新检查。");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    // Defer the first cache read until after the account page has painted so
    // this optional recovery panel never creates a synchronous effect render.
    const timer = window.setTimeout(() => void inspectDeviceHistory(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const count = totalCount(envelope);
  const sensitive = containsSensitiveHistory(envelope);

  const previewImport = useCallback(async (): Promise<void> => {
    if (!envelope || !count || busy) return;
    setBusy(true);
    setMessage("正在预览这台设备的记录…");
    try {
      const response = await requestWithTimeout("/api/mydairy/legacy-import/preview", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(envelope),
      });
      const payload = (await response.json().catch(() => null)) as unknown;
      if (!response.ok || !isImportResult(payload) || !payload.preview) {
        setMessage(failureMessage(response.status));
        return;
      }
      setPreview(payload.preview);
      if (!payload.preview.canApply) {
        setMessage("预览发现重复或无效记录，未导入任何内容；设备上的原记录仍保留。");
      } else if (payload.state === "completed" || payload.replayed) {
        setMessage("这台设备的这批记录此前已导入；设备上的原记录仍保留。");
      } else {
        setMessage(`预览完成：可导入 ${previewCount(payload.preview)} 条记录。确认后才会写入当前账号。`);
      }
    } catch {
      setMessage("网络暂时不可用；没有导入任何内容，设备上的原记录仍保留。");
    } finally {
      setBusy(false);
    }
  }, [busy, count, envelope]);

  useEffect(() => {
    // The person deliberately chose the recovery entry on the workbench. Make
    // that link truthfully open its non-mutating preview, while retaining the
    // final explicit import confirmation and all tenant/privacy checks.
    if (!previewOnArrival || autoPreviewConsumed.current || busy || preview || !envelope || !count) return;
    autoPreviewConsumed.current = true;
    void previewImport();
  }, [busy, count, envelope, preview, previewImport, previewOnArrival]);

  async function applyImport(): Promise<void> {
    if (!envelope || !preview?.canApply || !requestId || busy) return;
    setBusy(true);
    setMessage("正在导入到当前账号…请保持本页打开。");
    try {
      const response = await requestWithTimeout(`/api/mydairy/legacy-import/apply?request_id=${encodeURIComponent(requestId)}`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(envelope),
      });
      const payload = (await response.json().catch(() => null)) as unknown;
      if (!response.ok || !isImportResult(payload)) {
        setMessage(failureMessage(response.status));
        return;
      }
      setPreview(payload.preview ?? preview);
      if (payload.state !== "completed") {
        setMessage("导入尚未完成；这台设备上的原记录仍保留，可安全重试。");
        return;
      }
      setMessage(payload.replayed
        ? "这批记录已经导入，未重复新增；正在回到工作台读取你的历史。"
        : `已导入 ${payload.totalInserted ?? 0} 条记录；正在回到工作台读取你的历史。`,
      );
      window.setTimeout(() => window.location.assign(returnTo ?? "/?view=home"), 0);
    } catch {
      setMessage("网络暂时不可用；设备上的原记录仍保留，可稍后安全重试。");
    } finally {
      setBusy(false);
    }
  }

  const canPreview = Boolean(envelope && count && !busy);
  const canApply = Boolean(envelope && preview?.canApply && requestId && !busy);

  return (
    <section className="account-section" aria-label="本机历史导入">
      <p className="account-section-title">登录前本机历史</p>
      <p className="account-note">
        仅检查当前这台设备的匿名本机记录，不读取其他账号的数据。不会自动导入，也不会删除设备上的原记录。
        {sensitive ? " 其中包含敏感记录，需先在上方核对当前跨设备同步设置。" : ""}
      </p>
      <div className="account-actions">
        <button className="auth-google" disabled={busy} onClick={() => void inspectDeviceHistory()} type="button">
          {busy ? "正在检查…" : "重新检查本机历史"}
        </button>
        <button className="auth-primary-link" disabled={!canPreview} onClick={() => void previewImport()} type="button">
          预览导入内容
        </button>
        <button className="auth-google" disabled={!canApply} onClick={() => void applyImport()} type="button">
          确认导入到当前账号
        </button>
      </div>
      {preview ? (
        <p className="account-note">
          预览共 {previewCount(preview)} 条；重复项 {preview.duplicateIds?.length ?? 0}，无效项 {preview.invalidItems?.length ?? 0}。
        </p>
      ) : null}
      <p className="account-note" aria-live="polite">{message}</p>
      <p className="account-note">本机图片文件不会被本次导入上传或删除；需保留时可在工作台中重新选择上传。</p>
    </section>
  );
}
