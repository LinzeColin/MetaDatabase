"use client";

// P1-8 证据下钻三段式（UX_SPEC_EEI v1.0 §C.3）。任何「事实」元素（关系边 /
// 结构行 / 供应链关系 / 事件行）点开右栏都走这一个组件：
//   ① 结论：人话关系句（NVIDIA —[供应商]→ TSMC）
//   ② 摘录：evidence snippet + 定位（10-K 第 42 页 / Exhibit 21）
//   ③ 官方源：查看原文 ↗（SEC / GLEIF 真 URL，新窗口）
// 无证据不渲染死链（§C.3）；加载/空/错走五态组件；机器字段进〈诊断详情〉。

import { ExternalLink, X } from "lucide-react";
import type { ReactNode } from "react";

import type { EvidenceDetailRecord } from "../production-data-client";
import { EmptyState, ErrorState, Skeleton } from "./feedback";

export type EvidencePanelState = "loading" | "hydrated" | "error";

export function EvidencePanel({
  conclusion,
  state,
  record,
  reason,
  onClose,
  onRetry,
  testId
}: {
  /** ① 人话结论句（关系/事件的一句话陈述）。 */
  conclusion: ReactNode;
  state: EvidencePanelState;
  record: EvidenceDetailRecord | null;
  reason?: string;
  onClose?: () => void;
  onRetry?: () => void;
  testId?: string;
}) {
  const items = record?.evidence ?? [];
  return (
    <section className="evidencePanel" data-evidence-state={state} data-testid={testId}>
      <header className="evidencePanelHead">
        <div>
          <p className="eyebrow">证据 · 官方来源</p>
          <strong className="evidenceConclusion" data-testid={testId ? `${testId}-conclusion` : undefined}>
            {conclusion}
          </strong>
        </div>
        {onClose ? (
          <button aria-label="收起证据" className="iconButton pressable" onClick={onClose} type="button">
            <X aria-hidden="true" size={16} />
          </button>
        ) : null}
      </header>

      {state === "loading" ? <Skeleton count={3} variant="row" /> : null}

      {state === "error" ? (
        <ErrorState
          description="这条事实的官方来源暂时取不到，请稍后重试。"
          detail={reason}
          onRetry={onRetry}
          testId={testId ? `${testId}-error` : undefined}
          title="暂时取不到证据"
          tone="warn"
        />
      ) : null}

      {state === "hydrated" && items.length === 0 ? (
        <EmptyState
          description="这条关系尚未附上可公开的原文摘录——新证据核实后会出现在这里。"
          testId={testId ? `${testId}-empty` : undefined}
          title="暂无可展示的摘录"
          variant="collecting"
        />
      ) : null}

      {state === "hydrated" && items.length > 0 ? (
        <ol className="evidenceList" data-testid={testId ? `${testId}-list` : undefined}>
          {items.slice(0, 6).map((item, index) => (
            <li className="evidenceItem" key={item.evidence_id}>
              {/* ② 摘录 + 定位 */}
              <p className="evidenceExcerpt">
                {item.snippet.text || item.support_excerpt || "（该来源未提供可公开摘录）"}
              </p>
              <div className="evidenceMeta">
                {item.locator ? (
                  <small
                    className="evidenceLocator"
                    data-testid={testId ? `${testId}-locator-${index}` : undefined}
                  >
                    定位：{item.locator}
                  </small>
                ) : null}
                <span className="evidencePublisher">
                  {item.publisher || item.title || "官方文件"}
                </span>
              </div>
              {/* ③ 官方源链接（无 URL 则不渲染，杜绝裸下钻死链） */}
              {item.url ? (
                <a
                  className="evidenceSourceLink"
                  data-testid={testId ? `${testId}-source-${index}` : undefined}
                  href={item.url}
                  rel="noreferrer noopener"
                  target="_blank"
                >
                  查看官方原文
                  <ExternalLink aria-hidden="true" size={13} />
                </a>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}

      <details className="diagDetails">
        <summary>诊断详情</summary>
        <span>
          {state}
          {reason ? ` / ${reason}` : ""}
          {record ? ` / ${record.evidence_count} sources · ${record.source_document_count} docs` : ""}
        </span>
      </details>
    </section>
  );
}
