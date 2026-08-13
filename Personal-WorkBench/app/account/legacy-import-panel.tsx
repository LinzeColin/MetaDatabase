"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { requestWithTimeout } from "../_components/workbench/request-timeout";

type LegacyPreview = {
  canApply?: boolean;
  counts?: Record<string, number>;
  duplicateIds?: string[];
  invalidItems?: Array<unknown>;
};

type LegacyImportResult = {
  state?: "previewed" | "applying" | "completed" | "failed";
  preview?: LegacyPreview;
  replayed?: boolean;
  totalInserted?: number;
};

function newRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `legacy-import-${crypto.randomUUID()}`;
  }
  return `legacy-import-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isLegacyImportResult(value: unknown): value is LegacyImportResult {
  return isRecord(value) && (!value.preview || isRecord(value.preview));
}

function totalCount(preview: LegacyPreview | undefined): number {
  if (!preview?.counts) return 0;
  return Object.values(preview.counts).reduce((total, count) => total + (Number.isFinite(count) ? count : 0), 0);
}

function errorMessage(status: number): string {
  if (status === 401) return "登录状态已失效，请重新登录后再试。";
  if (status === 403) return "这份备份含敏感内容；请先在本页核对当前跨设备同步设置。";
  if (status === 409) return "备份中有重复或无效记录，无法导入。";
  if (status >= 500) return "迁移服务暂时不可用；本机源文件未改变，可稍后重试。";
  return "备份文件格式不受支持，请确认选择的是个人日程导出的 JSON 文件。";
}

/**
 * Deliberately requires an explicit file selection and confirmation. The page
 * never deletes or mutates the selected source file or browser storage.
 */
export function LegacyImportPanel() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [envelope, setEnvelope] = useState<unknown>(null);
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<LegacyPreview | null>(null);
  const [requestId, setRequestId] = useState("");
  const [message, setMessage] = useState("选择以前导出的 JSON 备份后，先查看预览再决定是否导入。");
  const [busy, setBusy] = useState(false);

  async function chooseFile(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.currentTarget.files?.[0];
    if (!file) return;

    setBusy(true);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as unknown;
      if (!isRecord(parsed)) throw new Error("not-an-object");
      setEnvelope(parsed);
      setFileName(file.name);
      setPreview(null);
      setRequestId(newRequestId());
      setMessage("备份已在当前页面读取。请先预览；源文件和原浏览器数据不会被删除。");
    } catch {
      setEnvelope(null);
      setFileName("");
      setPreview(null);
      setRequestId("");
      setMessage("无法读取该文件。请选择个人日程导出的 JSON 备份。原文件未改变。");
    } finally {
      setBusy(false);
    }
  }

  async function previewImport(): Promise<void> {
    if (!envelope || busy) return;
    setBusy(true);
    setMessage("正在检查备份内容…");
    try {
      const response = await requestWithTimeout("/api/mydairy/legacy-import/preview", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(envelope),
      });
      const payload = (await response.json().catch(() => null)) as unknown;
      if (!response.ok || !isLegacyImportResult(payload) || !payload.preview) {
        setMessage(errorMessage(response.status));
        return;
      }
      setPreview(payload.preview);
      if (!payload.preview.canApply) {
        setMessage("预览发现重复或无效记录；未写入任何历史数据，源文件仍保留。 ");
      } else if (payload.state === "completed" || payload.replayed) {
        setMessage("这份备份此前已完成导入；源文件仍保留在当前设备。");
      } else {
        setMessage(`预览完成：共 ${totalCount(payload.preview)} 条记录。确认后才会写入你的账户历史。`);
      }
    } catch {
      setMessage("网络暂时不可用；未写入任何历史数据，源文件仍保留，可稍后重试。 ");
    } finally {
      setBusy(false);
    }
  }

  async function applyImport(): Promise<void> {
    if (!envelope || !preview?.canApply || !requestId || busy) return;
    setBusy(true);
    setMessage("正在导入备份…请保持本页打开。 ");
    try {
      const response = await requestWithTimeout(`/api/mydairy/legacy-import/apply?request_id=${encodeURIComponent(requestId)}`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(envelope),
      });
      const payload = (await response.json().catch(() => null)) as unknown;
      if (!response.ok || !isLegacyImportResult(payload)) {
        setMessage(errorMessage(response.status));
        return;
      }
      setPreview(payload.preview ?? preview);
      if (payload.state === "completed") {
        setMessage(payload.replayed
          ? "这份备份已完成导入，未重复新增记录；源文件仍保留。"
          : `导入完成：新增 ${payload.totalInserted ?? 0} 条记录。源文件仍保留。`,
        );
      } else {
        setMessage("导入尚未完成；本机源文件仍保留，可重新预览后继续。 ");
      }
    } catch {
      setMessage("网络暂时不可用；导入可安全重试，源文件仍保留。 ");
    } finally {
      setBusy(false);
    }
  }

  const canApply = Boolean(envelope && preview?.canApply && requestId);

  return (
    <section className="account-section" aria-label="旧记录迁移">
      <p className="account-section-title">旧记录迁移</p>
      <p className="account-note">仅处理你主动选择的个人日程 JSON 备份。预览或导入都不会删除原文件或原浏览器数据。</p>
      <label className="legacy-import-file">
        <span>选择 JSON 备份</span>
        <input accept="application/json,.json" disabled={busy} onChange={(event) => void chooseFile(event)} ref={fileInput} type="file" />
      </label>
      {fileName ? <p className="account-note">已选择备份，等待预览。</p> : null}
      <div className="account-actions">
        <button className="auth-primary-link" disabled={!envelope || busy} onClick={() => void previewImport()} type="button">
          {busy ? "正在处理…" : "预览迁移内容"}
        </button>
        <button className="auth-google" disabled={!canApply || busy} onClick={() => void applyImport()} type="button">
          确认导入到我的历史
        </button>
      </div>
      {preview ? (
        <p className="account-note">
          预览共 {totalCount(preview)} 条；重复项 {preview.duplicateIds?.length ?? 0}，无效项 {preview.invalidItems?.length ?? 0}。
        </p>
      ) : null}
      <p className="account-note" aria-live="polite">{message}</p>
    </section>
  );
}
