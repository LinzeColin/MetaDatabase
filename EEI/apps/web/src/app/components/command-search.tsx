"use client";

// P1-5 全局搜索 Cmd+K（UX_SPEC_EEI v1.0 §C.1，Bloom "search-first" + OpenBB Cmd+K）。
// 自包含：既是顶栏搜索位（railTool 触发钮），又是 Portal 弹层本身。任意页
// 挂一个 <CommandSearch/> 即得：⌘K/Ctrl+K 唤起、输入 ≥2 字防抖 150ms 打
// GET /v1/entities?q=、↑↓ 选择 / Enter 落地图谱 / Esc 关闭。无结果走 §E.2 b 型。
// 落地方式：跳 /?subject={id}，商业版图以该实体为中心绽放并写面包屑。

import { Search } from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent
} from "react";
import { createPortal } from "react-dom";

import { EmptyState } from "./feedback";
import { zhLabel } from "../labels";
import { readProductionDataApiBaseUrl } from "../production-data-client";

type SearchEntity = {
  id: string;
  canonical_name: string;
  entity_type: string;
  status?: string;
};

type FetchState = "idle" | "loading" | "done" | "error";

const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 150;

export function CommandSearch() {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchEntity[]>([]);
  const [fetchState, setFetchState] = useState<FetchState>("idle");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    setMounted(true);
  }, []);

  const openPalette = useCallback(() => setOpen(true), []);
  const closePalette = useCallback(() => {
    setOpen(false);
    setQuery("");
    setResults([]);
    setFetchState("idle");
    setActiveIndex(0);
  }, []);

  // 全局 ⌘K / Ctrl+K 唤起（任意页）。已开则再次按下即关闭（toggle）。
  useEffect(() => {
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // 首页行业入口卡等外部入口可派发 eei:command-search-seed 预填并打开弹层
  // （search-first：一次点击进入搜索流，复用同一 Cmd+K 通道）。
  useEffect(() => {
    function onSeed(event: Event) {
      const detail = (event as CustomEvent<{ query?: string }>).detail;
      setQuery(typeof detail?.query === "string" ? detail.query : "");
      setOpen(true);
    }
    window.addEventListener("eei:command-search-seed", onSeed);
    return () => window.removeEventListener("eei:command-search-seed", onSeed);
  }, []);

  // 打开后聚焦输入框。
  useEffect(() => {
    if (open) {
      const timer = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [open]);

  // 防抖 150ms 查询（§C.1）。q<2 字不打接口；每次请求带序号，晚到的丢弃。
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResults([]);
      setFetchState("idle");
      setActiveIndex(0);
      return;
    }
    setFetchState("loading");
    const seq = ++requestSeq.current;
    const timer = window.setTimeout(async () => {
      const entities = await fetchEntities(trimmed);
      if (seq !== requestSeq.current) {
        return;
      }
      if (entities === null) {
        setFetchState("error");
        setResults([]);
        return;
      }
      setResults(entities);
      setActiveIndex(0);
      setFetchState("done");
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  const grouped = useMemo(() => groupByType(results), [results]);

  function commit(entity: SearchEntity | undefined) {
    if (!entity) {
      return;
    }
    closePalette();
    // 落地商业版图：以该实体为中心（graph 读 ?subject= 后 reroot + 写面包屑）。
    window.location.assign(`/?subject=${encodeURIComponent(entity.id)}`);
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (results.length ? (index + 1) % results.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) =>
        results.length ? (index - 1 + results.length) % results.length : 0
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      commit(results[activeIndex]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closePalette();
    }
  }

  const trimmedQuery = query.trim();
  const showNoResults =
    fetchState === "done" && results.length === 0 && trimmedQuery.length >= MIN_QUERY_LENGTH;

  return (
    <>
      <button
        aria-haspopup="dialog"
        aria-keyshortcuts="Meta+K Control+K"
        className="railTool pressable"
        data-testid="command-search-trigger"
        onClick={openPalette}
        title="全局搜索（⌘K / Ctrl+K）"
        type="button"
      >
        <Search aria-hidden="true" size={16} strokeWidth={1.8} />
        <span>搜索</span>
        <kbd>⌘K</kbd>
      </button>

      {mounted && open
        ? createPortal(
            <div
              className="cmdkOverlay"
              data-testid="command-search-overlay"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                  closePalette();
                }
              }}
              role="presentation"
            >
              <div
                aria-label="全局搜索"
                aria-modal="true"
                className="cmdkPanel"
                role="dialog"
              >
                <div className="cmdkInputRow">
                  <Search aria-hidden="true" size={18} />
                  <input
                    aria-controls="command-search-results"
                    autoComplete="off"
                    className="cmdkInput"
                    data-testid="command-search-input"
                    onChange={(event) => setQuery(event.target.value)}
                    onKeyDown={onInputKeyDown}
                    placeholder="搜索公司 / 人 / 设施，如 NVIDIA、TSMC、半导体"
                    ref={inputRef}
                    type="search"
                    value={query}
                  />
                  <kbd>Esc</kbd>
                </div>

                <div
                  className="cmdkResults"
                  data-testid="command-search-results"
                  id="command-search-results"
                  role="listbox"
                >
                  {trimmedQuery.length < MIN_QUERY_LENGTH ? (
                    <p className="cmdkHint">输入至少 2 个字符开始搜索。</p>
                  ) : null}

                  {fetchState === "loading" ? (
                    <p className="cmdkHint" data-testid="command-search-loading">
                      正在查询…
                    </p>
                  ) : null}

                  {fetchState === "error" ? (
                    <p className="cmdkHint" data-testid="command-search-error">
                      暂时连不上搜索服务，请稍后重试。
                    </p>
                  ) : null}

                  {showNoResults ? (
                    <EmptyState
                      actions={<a href="/objects-scope">查看数据覆盖范围</a>}
                      description={`没找到「${trimmedQuery}」。试试英文注册名或股票代码（如 NVIDIA、TSM）。`}
                      testId="command-search-no-results"
                      variant="no-results"
                    />
                  ) : null}

                  {grouped.map((group) => (
                    <div className="cmdkGroup" key={group.type}>
                      <p className="cmdkGroupLabel">{zhLabel("entity_type", group.type)}</p>
                      <ul>
                        {group.items.map((entity) => {
                          const flatIndex = results.indexOf(entity);
                          const active = flatIndex === activeIndex;
                          return (
                            <li key={entity.id}>
                              <button
                                aria-selected={active}
                                className={`cmdkResultRow${active ? " active" : ""}`}
                                data-active={active}
                                data-testid={`command-search-result-${entity.id}`}
                                onClick={() => commit(entity)}
                                onMouseEnter={() => setActiveIndex(flatIndex)}
                                role="option"
                                type="button"
                              >
                                <span className="cmdkResultName">
                                  {highlight(entity.canonical_name, trimmedQuery)}
                                </span>
                                <small>{zhLabel("entity_type", entity.entity_type)}</small>
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                </div>

                <footer className="cmdkFooter">
                  <span>
                    <kbd>↑</kbd>
                    <kbd>↓</kbd> 选择
                  </span>
                  <span>
                    <kbd>Enter</kbd> 打开
                  </span>
                  <span>
                    <kbd>Esc</kbd> 关闭
                  </span>
                </footer>
              </div>
            </div>,
            document.body
          )
        : null}
    </>
  );
}

async function fetchEntities(term: string): Promise<SearchEntity[] | null> {
  const apiBaseUrl = readProductionDataApiBaseUrl();
  if (!apiBaseUrl) {
    return null;
  }
  try {
    const response = await window.fetch(
      `${apiBaseUrl}/v1/entities?q=${encodeURIComponent(term)}`
    );
    const payload = (await response.json().catch(() => null)) as unknown;
    // 本地 API 返回裸数组；云 worker 包为 { query, entities: [...] }——两者都收。
    const list = Array.isArray(payload)
      ? payload
      : ((payload as { entities?: unknown } | null)?.entities ?? null);
    if (!response.ok || !Array.isArray(list)) {
      return null;
    }
    return list
      .filter(isSearchEntity)
      .slice(0, 30)
      .map((entity) => ({
        id: entity.id,
        canonical_name: entity.canonical_name,
        entity_type: entity.entity_type,
        status: typeof entity.status === "string" ? entity.status : undefined
      }));
  } catch {
    return null;
  }
}

function isSearchEntity(value: unknown): value is SearchEntity {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.id === "string" &&
    typeof record.canonical_name === "string" &&
    typeof record.entity_type === "string"
  );
}

// 按类型分组，每组最多 5 条（§C.1）；组顺序按结果首次出现的类型稳定排列。
function groupByType(entities: SearchEntity[]): { type: string; items: SearchEntity[] }[] {
  const order: string[] = [];
  const buckets = new Map<string, SearchEntity[]>();
  for (const entity of entities) {
    const type = entity.entity_type;
    if (!buckets.has(type)) {
      buckets.set(type, []);
      order.push(type);
    }
    const bucket = buckets.get(type)!;
    if (bucket.length < 5) {
      bucket.push(entity);
    }
  }
  return order.map((type) => ({ type, items: buckets.get(type) ?? [] }));
}

// 匹配段高亮（大小写不敏感）。返回带 <mark> 的片段数组。
function highlight(name: string, term: string) {
  if (!term) {
    return name;
  }
  const lowerName = name.toLowerCase();
  const lowerTerm = term.toLowerCase();
  const start = lowerName.indexOf(lowerTerm);
  if (start < 0) {
    return name;
  }
  const end = start + term.length;
  return (
    <>
      {name.slice(0, start)}
      <mark>{name.slice(start, end)}</mark>
      {name.slice(end)}
    </>
  );
}
