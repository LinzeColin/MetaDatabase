"use client";

// P1-6 五态统一组件库（UX_SPEC_EEI v1.0 §B.1）。
// 全站唯一的加载/成功/失败/空/陈旧反馈来源，替换各页手写状态块。
// 参数照抄 Grafana Saga：骨架延迟 100ms 出现（快返回则完全不见）、刷新
// 进度条延迟 300ms、刷新不清屏（旧数据保留可见）；错误分三层、标题必填
// 人话、机器码收进〈诊断详情〉；空态四变体，no-results 动态出现挂 role=alert。
// 所有动效走 globals.css 的 --motion-* token，reduced-motion 总闸自动全灭。

import { AlertTriangle, RefreshCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

/**
 * 延迟显形闸门：仅当 `active` 连续保持 `delayMs` 后才返回 true。
 * active 变 false 立即复位——快请求（<delay）全程返回 false，杜绝闪烁。
 */
function useDelayedFlag(active: boolean, delayMs: number): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!active) {
      setShown(false);
      return;
    }
    const timer = window.setTimeout(() => setShown(true), delayMs);
    return () => window.clearTimeout(timer);
  }, [active, delayMs]);
  return shown;
}

// —— 加载：同构骨架屏（§B.1，延迟 100ms 出现）——————————————————————
export type SkeletonVariant = "card" | "row" | "stat" | "text";

export function Skeleton({
  variant = "card",
  count = 3,
  testId
}: {
  variant?: SkeletonVariant;
  count?: number;
  testId?: string;
}) {
  // 从挂载起计时；100ms 内被卸载（数据已返回）则从未显形（Grafana 防闪烁）。
  const shown = useDelayedFlag(true, 100);
  return (
    <div
      aria-hidden="true"
      className="feedbackSkeleton"
      data-shown={shown}
      data-skeleton-variant={variant}
      data-testid={testId}
    >
      {shown
        ? Array.from({ length: Math.max(1, count) }).map((_, index) => (
            <span className={`skeletonBar skeletonBar--${variant}`} key={index} />
          ))
        : null}
    </div>
  );
}

// —— 刷新：顶部 1px 进度条（§B.1，延迟 300ms，不清屏）—————————————————
export function TopLoadingBar({ active, testId }: { active: boolean; testId?: string }) {
  const shown = useDelayedFlag(active, 300);
  return (
    <div
      aria-hidden="true"
      className="feedbackTopBar"
      data-active={shown}
      data-testid={testId}
    >
      {shown ? <span className="feedbackTopBarTrack" /> : null}
    </div>
  );
}

// —— 失败：三层分级（§B.1，标题必填人话、reason 进诊断详情）——————————————
export type ErrorLevel = "inline" | "badge" | "global";

export function ErrorState({
  level = "inline",
  tone = "error",
  title,
  description,
  detail,
  onRetry,
  retryLabel = "重试",
  testId,
  retryTestId
}: {
  level?: ErrorLevel;
  tone?: "warn" | "error";
  title: string;
  description?: ReactNode;
  /** 机器错误码 / reason 字符串——只进〈诊断详情〉，绝不直出正文。 */
  detail?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  testId?: string;
  retryTestId?: string;
}) {
  if (level === "badge") {
    return (
      <span
        className={`feedbackBadge tone-${tone}`}
        data-testid={testId}
        role="status"
        title={typeof description === "string" ? description : title}
      >
        <AlertTriangle aria-hidden="true" size={13} />
        {title}
      </span>
    );
  }
  return (
    <section
      className={`feedbackState feedbackError tone-${tone} level-${level}`}
      data-testid={testId}
      role="alert"
    >
      <div className="feedbackHead">
        <AlertTriangle aria-hidden="true" size={18} />
        <strong>{title}</strong>
      </div>
      {description ? <p className="feedbackBody">{description}</p> : null}
      {onRetry ? (
        <button
          className="feedbackRetry pressable"
          data-testid={retryTestId}
          onClick={onRetry}
          type="button"
        >
          <RefreshCw aria-hidden="true" size={14} />
          {retryLabel}
        </button>
      ) : null}
      {detail ? (
        <details className="diagDetails">
          <summary>诊断详情</summary>
          <span>{detail}</span>
        </details>
      ) : null}
    </section>
  );
}

// —— 空：四变体（§B.1 + §E.2 模板，先判空因再选型）——————————————————————
export type EmptyVariant = "collecting" | "no-results" | "not-created" | "caught-up";

export function EmptyState({
  variant,
  title,
  description,
  actions,
  testId
}: {
  variant: EmptyVariant;
  title?: string;
  description?: ReactNode;
  /** 结构强制三段之「你可以做什么」——传按钮/链接。 */
  actions?: ReactNode;
  testId?: string;
}) {
  // no-results（筛选/搜索无结果）是动态出现的态：无障碍需要 role=alert 播报。
  const dynamic = variant === "no-results";
  return (
    <section
      className={`feedbackState feedbackEmpty variant-${variant}`}
      data-empty-variant={variant}
      data-testid={testId}
      role={dynamic ? "alert" : undefined}
    >
      {title ? <strong className="feedbackEmptyTitle">{title}</strong> : null}
      {description ? <div className="feedbackBody">{description}</div> : null}
      {actions ? <div className="feedbackActions">{actions}</div> : null}
    </section>
  );
}

// —— 陈旧：更新于 + 滞后琥珀点（§B.1）——————————————————————————————————
export function StaleBadge({
  updatedAt,
  stale = false,
  testId
}: {
  updatedAt?: string | null;
  stale?: boolean;
  testId?: string;
}) {
  return (
    <span
      className={`feedbackStale${stale ? " isStale" : ""}`}
      data-stale={stale}
      data-testid={testId}
      title={stale ? "数据可能滞后" : undefined}
    >
      {stale ? <span aria-hidden="true" className="feedbackStaleDot" /> : null}
      更新于 {formatUpdatedAt(updatedAt)}
    </span>
  );
}

/** as_of / activated_at → 「MM-DD HH:mm」；无值显示占位。 */
function formatUpdatedAt(value?: string | null): string {
  if (!value) {
    return "载入中";
  }
  // 形如 2026-07-17T05:50:12Z → 07-17 05:50（24 制，§E.3 第 4 条）。
  const match = value.match(/^\d{4}-(\d{2}-\d{2})[T\s](\d{2}:\d{2})/);
  if (match) {
    return `${match[1]} ${match[2]}`;
  }
  return value.slice(0, 16).replace("T", " ");
}
