"use client";

// P2-9 「我的」抽屉（UX_SPEC_EEI v1.0 §A.2 顶栏 / §G-P2-9）。
// 关注 + 保存视图 + 探索记录三 tab 合一；顶栏铃铛未读角标（/v1/changes）。
// 关注/取消关注乐观更新：本地先变、失败回滚 + 错误反馈走 feedback.tsx ErrorState。
// 抽屉动效走 --motion-slow / --ease-emphatic（§D.2），reduced-motion 经
// --motion-scale 总闸自动近乎瞬时。未配置数据接口时各 tab 显示诚实空态。

import { Bell, Bookmark, History, Star, UserRound, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { EmptyState, ErrorState, Skeleton, StaleBadge } from "./feedback";
import {
  ensureDefaultWatchlist,
  followEntity,
  loadExplorationLog,
  loadSavedViews,
  loadUnreadCount,
  loadWatchlists,
  unfollowEntity,
  type ExplorationLogEntry,
  type SavedViewSummary,
  type WatchlistRecord
} from "../my-drawer-client";

type DrawerTab = "watchlist" | "saved" | "history";
type PaneState = "idle" | "loading" | "ok" | "empty" | "error";

/** 关注事件桥：图谱侧「加入关注」按钮派发，抽屉接住做乐观关注。 */
export type WatchlistFollowDetail = { entity_id: string; label?: string };

const EXPLORATION_ACTION_LABELS: Record<string, string> = {
  reroot: "换中心",
  expand: "展开",
  start: "开始探索",
  restore: "恢复视图",
  explore: "探索"
};

export function MyDrawer() {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<DrawerTab>("watchlist");

  const [watchlists, setWatchlists] = useState<WatchlistRecord[]>([]);
  const [watchState, setWatchState] = useState<PaneState>("idle");
  const [savedViews, setSavedViews] = useState<SavedViewSummary[]>([]);
  const [savedState, setSavedState] = useState<PaneState>("idle");
  const [logEntries, setLogEntries] = useState<ExplorationLogEntry[]>([]);
  const [logState, setLogState] = useState<PaneState>("idle");

  const [unread, setUnread] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // 序号：晚到的响应不得覆盖新一轮乐观状态（防竞态，e2e 稳定性）。
  const followSeq = useRef(0);
  // 关注列表「已拉过一次」闸门：防打开事件与关注事件重复拉取——后者的
  // 服务端结果会把前者的乐观插入覆盖掉（race）。ref 镜像供乐观关注读最新列表。
  const watchLoadedRef = useRef(false);
  const watchlistsRef = useRef<WatchlistRecord[]>([]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    watchlistsRef.current = watchlists;
  }, [watchlists]);

  const refreshUnread = useCallback(async () => {
    setUnread(await loadUnreadCount());
  }, []);

  const hydrateWatchlists = useCallback(async (): Promise<WatchlistRecord[]> => {
    watchLoadedRef.current = true;
    setWatchState("loading");
    const result = await loadWatchlists();
    if (result.status === "ok") {
      setWatchlists(result.data);
      setWatchState(result.data.some((list) => list.items.length > 0) ? "ok" : "empty");
      return result.data;
    }
    if (result.status === "empty") {
      setWatchState("empty");
    } else {
      setWatchState("error");
    }
    return [];
  }, []);

  const hydrateSaved = useCallback(async () => {
    setSavedState("loading");
    const result = await loadSavedViews();
    if (result.status === "ok") {
      setSavedViews(result.data);
      setSavedState(result.data.length ? "ok" : "empty");
    } else if (result.status === "empty") {
      setSavedState("empty");
    } else {
      setSavedState("error");
    }
  }, []);

  const hydrateLog = useCallback(async () => {
    setLogState("loading");
    const result = await loadExplorationLog(20);
    if (result.status === "ok") {
      setLogEntries(result.data);
      setLogState(result.data.length ? "ok" : "empty");
    } else if (result.status === "empty") {
      setLogState("empty");
    } else {
      setLogState("error");
    }
  }, []);

  // 铃铛未读数在挂载即拉一次（顶栏角标不依赖抽屉打开）。
  useEffect(() => {
    void refreshUnread();
  }, [refreshUnread]);

  // 打开时按当前 tab 懒加载；已加载过的 tab 不重复请求。
  useEffect(() => {
    if (!open) {
      return;
    }
    if (tab === "watchlist" && !watchLoadedRef.current) {
      void hydrateWatchlists();
    } else if (tab === "saved" && savedState === "idle") {
      void hydrateSaved();
    } else if (tab === "history" && logState === "idle") {
      void hydrateLog();
    }
  }, [open, tab, savedState, logState, hydrateWatchlists, hydrateSaved, hydrateLog]);

  const applyOptimisticFollow = useCallback(
    async (detail: WatchlistFollowDetail) => {
      const entityId = detail.entity_id;
      if (!entityId) {
        return;
      }
      setActionError(null);
      // 需要先有列表才能落点：未拉过则拉一次（并占住 watchLoadedRef，防打开
      // 事件重复拉取覆盖乐观插入）；已拉过则读 ref 里的最新列表。
      const lists = watchLoadedRef.current
        ? watchlistsRef.current
        : await hydrateWatchlists();
      const ensured = await ensureDefaultWatchlist(lists);
      if (ensured.status !== "ok") {
        setActionError(ensured.reason);
        return;
      }
      const listId = ensured.id;
      const seq = ++followSeq.current;
      // 回滚快照取本轮操作的列表基线（刚加载/ref 镜像），插入前的状态。
      const snapshot = lists;
      const already = snapshot.some((list) =>
        list.items.some((item) => item.entity_id === entityId)
      );
      if (!already) {
        // 乐观：本地先插入（functional update，不受闭包旧值影响）。
        setWatchlists((current) => upsertList(current, listId, detail));
        setWatchState("ok");
      }
      const result = await followEntity(listId, entityId);
      if (seq !== followSeq.current) {
        return;
      }
      if (result.status === "error") {
        // 回滚到快照，报错走 ErrorState。
        setWatchlists(snapshot);
        setWatchState(snapshot.some((list) => list.items.length > 0) ? "ok" : "empty");
        setActionError(result.reason);
      }
    },
    [hydrateWatchlists]
  );

  // 图谱侧「加入关注」→ eei:watchlist-follow → 抽屉乐观关注（并打开抽屉让用户看到回执）。
  useEffect(() => {
    function onFollow(event: Event) {
      const detail = (event as CustomEvent<WatchlistFollowDetail>).detail;
      if (!detail?.entity_id) {
        return;
      }
      setOpen(true);
      setTab("watchlist");
      void applyOptimisticFollow(detail);
    }
    window.addEventListener("eei:watchlist-follow", onFollow);
    return () => window.removeEventListener("eei:watchlist-follow", onFollow);
  }, [applyOptimisticFollow]);

  async function handleUnfollow(listId: string, entityId: string) {
    setActionError(null);
    const seq = ++followSeq.current;
    const snapshot = watchlists;
    // 乐观移除。
    setWatchlists((current) =>
      current.map((list) =>
        list.id === listId
          ? { ...list, items: list.items.filter((item) => item.entity_id !== entityId) }
          : list
      )
    );
    const result = await unfollowEntity(listId, entityId);
    if (seq !== followSeq.current) {
      return;
    }
    if (result.status === "error") {
      // 回滚到快照，报错走 ErrorState。
      setWatchlists(snapshot);
      setActionError(result.reason);
    }
    // 成功时无需改 watchState：WatchlistPane 在 items 清零时自动切空态。
  }

  function openDrawer() {
    setOpen(true);
    void refreshUnread();
  }

  function closeDrawer() {
    setOpen(false);
  }

  const followedCount = watchlists.reduce((total, list) => total + list.items.length, 0);

  return (
    <>
      <button
        aria-haspopup="dialog"
        className="railTool pressable"
        data-testid="my-drawer-trigger"
        data-unread={unread ?? 0}
        onClick={openDrawer}
        title="我的（关注 · 保存视图 · 探索记录）"
        type="button"
      >
        <UserRound size={16} strokeWidth={1.8} aria-hidden="true" />
        <span>我的</span>
        {unread && unread > 0 ? (
          <span className="myDrawerBellBadge" data-testid="my-drawer-unread-badge">
            <Bell size={11} aria-hidden="true" />
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </button>

      {mounted && open
        ? createPortal(
            <div
              className="myDrawerOverlay"
              data-testid="my-drawer-overlay"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                  closeDrawer();
                }
              }}
              role="presentation"
            >
              <aside
                aria-label="我的"
                aria-modal="true"
                className="myDrawerPanel"
                data-testid="my-drawer-panel"
                role="dialog"
              >
                <header className="myDrawerHead">
                  <div>
                    <p className="eyebrow">我的</p>
                    <h2>关注 · 视图 · 记录</h2>
                  </div>
                  <button
                    aria-label="关闭"
                    className="myDrawerClose pressable"
                    data-testid="my-drawer-close"
                    onClick={closeDrawer}
                    type="button"
                  >
                    <X size={18} aria-hidden="true" />
                  </button>
                </header>

                <div className="myDrawerTabs" role="tablist">
                  <DrawerTabButton
                    active={tab === "watchlist"}
                    badge={followedCount}
                    icon={<Star size={15} aria-hidden="true" />}
                    label="关注"
                    onSelect={() => setTab("watchlist")}
                    testId="my-drawer-tab-watchlist"
                  />
                  <DrawerTabButton
                    active={tab === "saved"}
                    icon={<Bookmark size={15} aria-hidden="true" />}
                    label="保存视图"
                    onSelect={() => setTab("saved")}
                    testId="my-drawer-tab-saved"
                  />
                  <DrawerTabButton
                    active={tab === "history"}
                    icon={<History size={15} aria-hidden="true" />}
                    label="探索记录"
                    onSelect={() => setTab("history")}
                    testId="my-drawer-tab-history"
                  />
                </div>

                <div className="myDrawerBody">
                  {actionError ? (
                    <ErrorState
                      description="关注操作没有成功，已还原。请稍后重试。"
                      detail={actionError}
                      level="inline"
                      testId="my-drawer-action-error"
                      title="操作没有成功"
                      tone="error"
                    />
                  ) : null}

                  {tab === "watchlist" ? (
                    <WatchlistPane
                      onUnfollow={handleUnfollow}
                      state={watchState}
                      watchlists={watchlists}
                    />
                  ) : null}
                  {tab === "saved" ? (
                    <SavedPane state={savedState} views={savedViews} />
                  ) : null}
                  {tab === "history" ? (
                    <HistoryPane entries={logEntries} state={logState} />
                  ) : null}
                </div>
              </aside>
            </div>,
            document.body
          )
        : null}
    </>
  );
}

function DrawerTabButton({
  active,
  badge,
  icon,
  label,
  onSelect,
  testId
}: {
  active: boolean;
  badge?: number;
  icon: React.ReactNode;
  label: string;
  onSelect: () => void;
  testId: string;
}) {
  return (
    <button
      aria-selected={active}
      className={`myDrawerTab pressable${active ? " active" : ""}`}
      data-active={active}
      data-testid={testId}
      onClick={onSelect}
      role="tab"
      type="button"
    >
      {icon}
      <span>{label}</span>
      {badge ? <em>{badge}</em> : null}
    </button>
  );
}

function WatchlistPane({
  onUnfollow,
  state,
  watchlists
}: {
  onUnfollow: (listId: string, entityId: string) => void;
  state: PaneState;
  watchlists: WatchlistRecord[];
}) {
  if (state === "loading") {
    return <Skeleton count={3} testId="my-drawer-watchlist-skeleton" variant="row" />;
  }
  if (state === "error") {
    return (
      <ErrorState
        description="关注列表加载没有成功，请稍后重试。"
        level="inline"
        testId="my-drawer-watchlist-error"
        title="加载没有成功"
        tone="error"
      />
    );
  }
  const items = watchlists.flatMap((list) =>
    list.items.map((item) => ({ listId: list.id, ...item }))
  );
  if (state === "empty" || items.length === 0) {
    return (
      <EmptyState
        actions={<a href="/">去图谱看看</a>}
        description="还没有关注任何公司。在图谱中选中实体后点「加入关注」，变化会在这里汇总。"
        testId="my-drawer-watchlist-empty"
        title="还没有关注"
        variant="not-created"
      />
    );
  }
  return (
    <ul className="myDrawerList" data-testid="my-drawer-watchlist">
      {items.map((item) => (
        <li className="myDrawerWatchItem" data-testid={`my-drawer-watch-item-${item.entity_id}`} key={item.entity_id}>
          <a className="myDrawerWatchLink" href={`/?subject=${encodeURIComponent(item.entity_id)}`}>
            <Star size={13} aria-hidden="true" />
            <span>{item.label ?? shortEntity(item.entity_id)}</span>
          </a>
          <button
            aria-label="取消关注"
            className="myDrawerUnfollow pressable"
            data-testid={`my-drawer-unfollow-${item.entity_id}`}
            onClick={() => onUnfollow(item.listId, item.entity_id)}
            title="取消关注"
            type="button"
          >
            <X size={14} aria-hidden="true" />
          </button>
        </li>
      ))}
    </ul>
  );
}

function SavedPane({ state, views }: { state: PaneState; views: SavedViewSummary[] }) {
  if (state === "loading") {
    return <Skeleton count={3} testId="my-drawer-saved-skeleton" variant="row" />;
  }
  if (state === "error") {
    return (
      <ErrorState
        description="保存视图加载没有成功，请稍后重试。"
        level="inline"
        testId="my-drawer-saved-error"
        title="加载没有成功"
        tone="error"
      />
    );
  }
  if (state === "empty" || views.length === 0) {
    return (
      <EmptyState
        actions={<a href="/">去图谱保存一个视图</a>}
        description="还没有保存任何视图。在图谱中调好焦点与筛选后保存，就能在这里一键恢复。"
        testId="my-drawer-saved-empty"
        title="还没有保存视图"
        variant="not-created"
      />
    );
  }
  return (
    <ul className="myDrawerList" data-testid="my-drawer-saved">
      {views.map((view) => (
        <li className="myDrawerSavedItem" data-testid={`my-drawer-saved-item-${view.id}`} key={view.id}>
          <Bookmark size={13} aria-hidden="true" />
          <span className="myDrawerSavedName">{view.name}</span>
          {view.updated_at ? <StaleBadge updatedAt={view.updated_at} /> : null}
        </li>
      ))}
    </ul>
  );
}

function HistoryPane({
  entries,
  state
}: {
  entries: ExplorationLogEntry[];
  state: PaneState;
}) {
  if (state === "loading") {
    return <Skeleton count={4} testId="my-drawer-history-skeleton" variant="row" />;
  }
  if (state === "error") {
    return (
      <ErrorState
        description="探索记录加载没有成功，请稍后重试。"
        level="inline"
        testId="my-drawer-history-error"
        title="加载没有成功"
        tone="error"
      />
    );
  }
  if (state === "empty" || entries.length === 0) {
    return (
      <EmptyState
        description="还没有探索记录。在图谱中换中心、展开关系，足迹会记录在这里。"
        testId="my-drawer-history-empty"
        title="还没有探索记录"
        variant="caught-up"
      />
    );
  }
  return (
    <ol className="myDrawerList" data-testid="my-drawer-history">
      {entries.map((entry) => (
        <li className="myDrawerHistItem" data-testid={`my-drawer-hist-item-${entry.id}`} key={entry.id}>
          <span className="myDrawerHistAction">
            {EXPLORATION_ACTION_LABELS[entry.action] ?? entry.action}
          </span>
          <span className="myDrawerHistTarget">
            {entry.label ?? (entry.focus_entity_id ? shortEntity(entry.focus_entity_id) : "—")}
          </span>
          {entry.created_at ? <StaleBadge updatedAt={entry.created_at} /> : null}
        </li>
      ))}
    </ol>
  );
}

function upsertList(
  lists: WatchlistRecord[],
  listId: string,
  detail: WatchlistFollowDetail
): WatchlistRecord[] {
  const item = { entity_id: detail.entity_id, label: detail.label ?? null, added_at: null };
  const existingIndex = lists.findIndex((list) => list.id === listId);
  if (existingIndex < 0) {
    return [...lists, { id: listId, name: "我的关注", created_at: null, items: [item] }];
  }
  return lists.map((list) =>
    list.id === listId ? { ...list, items: [...list.items, item] } : list
  );
}

function shortEntity(id: string): string {
  if (id.length <= 12) {
    return id;
  }
  return `${id.slice(0, 8)}…${id.slice(-4)}`;
}
