"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { safeAccountReturnPath } from "../_components/workbench/account-return-path";
import { LegacyDomainRedirect } from "../_components/workbench/legacy-domain-redirect";
import { DeviceHistoryTransferPanel } from "./device-history-transfer-panel";
import { LegacyImportPanel } from "./legacy-import-panel";

type Account = { id: string; providerId: string };
type Session = { user: { name: string; email: string; emailVerified: boolean } } | null;
type PrivacyState = "not_requested" | "accepted" | "revoked";
type PrivacySnapshot = {
  state: PrivacyState;
  consentedAt: number | null;
  revokedAt: number | null;
  policyVersion: string | null;
  currentVersion: string;
  deletionState: "active" | "pending" | null;
  noticeSha256?: string | null;
  legalOperatorName?: string | null;
  privacyContactEmail?: string | null;
};
type DeletionState = "active" | "pending";
type SyncHealth = "checking" | "idle" | "ready" | "unavailable";

type ExportResponse = {
  data: Record<string, unknown>;
  exportHash: string;
};

function prettyDate(value: number | null): string {
  if (!value) return "未发生";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "无效时间";
  return date.toLocaleString("zh-CN");
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "{}";
  }
}

export default function AccountPage() {
  const [session, setSession] = useState<Session>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [message, setMessage] = useState("正在确认账户状态…");
  const [privacy, setPrivacy] = useState<PrivacySnapshot>({
    state: "not_requested",
    consentedAt: null,
    revokedAt: null,
    policyVersion: null,
    currentVersion: "policy-2026-08-05-v1",
    deletionState: "active",
    legalOperatorName: null,
    privacyContactEmail: null,
  });
  const [deletion, setDeletion] = useState<DeletionState>("active");
  const [deletionToken, setDeletionToken] = useState("");
  const [tokenExpiresAt, setTokenExpiresAt] = useState<number | null>(null);
  const [exported, setExported] = useState("");
  const [exportHash, setExportHash] = useState("");
  const [privacyNoticeHash, setPrivacyNoticeHash] = useState("e".repeat(64));
  const [requiresFreshLogin, setRequiresFreshLogin] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [syncHealth, setSyncHealth] = useState<SyncHealth>("idle");
  const returnTo = typeof window === "undefined"
    ? null
    : safeAccountReturnPath(new URLSearchParams(window.location.search).get("return_to"));

  /**
   * This is a deliberately data-free, verified-session-only check. The route
   * executes a constant D1 statement and a private R2 head request, so a
   * person can distinguish an unavailable sync service from empty history
   * without exposing any table, object, account, or storage identifier.
   */
  const checkSyncHealth = useCallback(async () => {
    setSyncHealth("checking");
    try {
      const response = await fetch("/storage-check", { credentials: "same-origin" });
      if (!response.ok) {
        setSyncHealth("unavailable");
        return;
      }
      const document = await response.text();
      setSyncHealth(
        document.includes('data-d1="available"') && document.includes('data-r2="available"')
          ? "ready"
          : "unavailable",
      );
    } catch {
      setSyncHealth("unavailable");
    }
  }, []);

  const loadAccount = useCallback(async () => {
    try {
      // A Google callback may upgrade the database user immediately while an
      // older browser session snapshot still says emailVerified=false. Account
      // settings decide whether sensitive records may sync, so they must read
      // the current server-side session rather than that stale snapshot.
      const sessionResponse = await fetch("/api/auth/get-session?disableCookieCache=true", { credentials: "same-origin" });
      if (!sessionResponse.ok) {
        setMessage("请先登录后再管理账户。");
        return;
      }
      const nextSession = (await sessionResponse.json()) as Session;
      if (!nextSession?.user) {
        setMessage("请先登录后再管理账户。");
        return;
      }
      if (!nextSession.user.emailVerified) {
        setMessage("请先完成邮箱验证。");
        return;
      }
      setSession(nextSession);
      void checkSyncHealth();

      const accountResponse = await fetch("/api/auth/list-accounts", { credentials: "same-origin" });
      if (accountResponse.ok) {
        setAccounts((await accountResponse.json()) as Account[]);
      }

      const privacyResponse = await fetch("/api/account/privacy", { credentials: "same-origin" });
      if (privacyResponse.ok) {
        const snapshot = (await privacyResponse.json()) as PrivacySnapshot;
        setPrivacy({
          state: snapshot.state,
          consentedAt: snapshot.consentedAt ?? null,
          revokedAt: snapshot.revokedAt ?? null,
          policyVersion: snapshot.policyVersion ?? null,
          currentVersion: snapshot.currentVersion,
          deletionState: snapshot.deletionState ?? "active",
          legalOperatorName: snapshot.legalOperatorName ?? null,
          privacyContactEmail: snapshot.privacyContactEmail ?? null,
        });
        setPrivacyNoticeHash(snapshot.noticeSha256 ?? "e".repeat(64));
      }

      const deletionResponse = await fetch("/api/account/delete", { credentials: "same-origin" });
      if (deletionResponse.ok) {
        const deletionInfo = (await deletionResponse.json()) as { state: DeletionState; tokenExpiresAt: number | null };
        setDeletion(deletionInfo.state);
        setTokenExpiresAt(deletionInfo.tokenExpiresAt);
      }

      setMessage("");
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    }
  }, [checkSyncHealth]);

  useEffect(() => {
    void (async () => {
      await loadAccount();
    })();
  }, [loadAccount]);

  async function linkGoogle() {
    if (isBusy) return;
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch("/api/auth/link-social", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ provider: "google", callbackURL: "/account" }),
      });
      const result = (await response.json().catch(() => null)) as { url?: string } | null;
      if (response.ok && typeof result?.url === "string") {
        window.location.assign(result.url);
        return;
      }
      setMessage("暂时无法连接 Google，请稍后再试。");
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    } finally {
      setIsBusy(false);
    }
  }

  async function signOut() {
    if (isBusy) return;
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch("/api/auth/sign-out", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({}),
      });
      if (!response.ok) {
        setMessage("退出登录失败，请稍后再试。");
        return;
      }
      setSession(null);
      setAccounts([]);
      window.location.assign("/auth/sign-in?signed_out=1");
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    } finally {
      setIsBusy(false);
    }
  }

  async function setConsent(decision: "accepted" | "revoked") {
    if (!session || isBusy) return;
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch("/api/account/privacy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          decision,
          policyVersion: privacy.currentVersion,
          noticeSha256: privacyNoticeHash,
        }),
      });
      const body = (await response.json().catch(() => null)) as {
        state?: PrivacyState;
        policyVersion?: string | null;
        decidedAt?: number | null;
        message?: string;
      };
      if (!response.ok) {
        setMessage(body?.message ?? "隐私设置更新失败。");
        return;
      }
      await loadAccount();
      if (decision === "accepted") {
        window.dispatchEvent(new Event("mydairy:privacy-consent-accepted"));
        if (returnTo) {
          setMessage("已开启敏感内容跨设备保存，正在返回原页面同步你的历史记录…");
          window.setTimeout(() => window.location.assign(returnTo), 0);
        } else {
          setMessage("已开启敏感内容跨设备保存。返回记录页后，本设备当前账号暂存的敏感记录会自动同步。");
        }
      }
      else setMessage("已关闭敏感内容跨设备保存。");
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    } finally {
      setIsBusy(false);
    }
  }

  async function requestDeletion() {
    if (!session || isBusy) return;
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch("/api/account/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ action: "request" }),
      });
      const body = (await response.json().catch(() => null)) as
        | { action: string; recoveryToken?: string; exportHash?: string; tokenExpiresAt?: number | null }
        | null;
      if (!response.ok || !body || body.action !== "request") {
        if (response.status === 403) {
          setRequiresFreshLogin(true);
          setMessage("为保护账户安全，请重新登录后再开始删除。");
        } else {
          setMessage("删除请求失败，请重试。");
        }
        return;
      }
      setDeletionToken(body.recoveryToken ?? "");
      setDeletion("pending");
      setTokenExpiresAt(body.tokenExpiresAt ?? null);
      setMessage("已进入待确认状态，已返回恢复口令（本地暂存）；请在 24 小时内确认或撤销。");
      if (body.exportHash) setExportHash(body.exportHash);
      await loadAccount();
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    } finally {
      setIsBusy(false);
    }
  }

  async function confirmDeletion() {
    if (!session || isBusy || !deletionToken) return;
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch("/api/account/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ action: "confirm", recoveryToken: deletionToken }),
      });
      if (response.ok) {
        setDeletion("active");
        setMessage("账户已删除，请退出并刷新页面确认。");
        setDeletionToken("");
      } else {
        if (response.status === 403) {
          setRequiresFreshLogin(true);
          setMessage("为保护账户安全，请重新登录后再确认删除。");
        } else {
          setMessage("删除确认失败，请使用恢复口令重试。");
        }
      }
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    } finally {
      setIsBusy(false);
    }
  }

  async function undoDeletion() {
    if (!session || isBusy || !deletionToken) return;
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch("/api/account/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ action: "undo", recoveryToken: deletionToken }),
      });
      if (response.ok) {
        setDeletion("active");
        setDeletionToken("");
        setExportHash("");
        await loadAccount();
        setMessage("已撤销账户删除，状态恢复正常。");
      } else {
        if (response.status === 403) {
          setRequiresFreshLogin(true);
          setMessage("为保护账户安全，请重新登录后再撤销删除。");
        } else {
          setMessage("撤销失败，请重新请求删除后再试。");
        }
      }
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    } finally {
      setIsBusy(false);
    }
  }

  async function exportAccount() {
    if (!session || isBusy) return;
    setMessage("");
    setIsBusy(true);
    try {
      const response = await fetch("/api/account/export", { credentials: "same-origin" });
      const body = (await response.json().catch(() => null)) as ExportResponse | null;
      if (!response.ok || !body) {
        setMessage("导出失败，请稍后再试。");
        return;
      }
      setExported(prettyJson(body.data));
      setExportHash(body.exportHash);
      setMessage("导出完成，可在下方复制 JSON 与校验摘要。");
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    } finally {
      setIsBusy(false);
    }
  }

  const isPendingDelete = deletion === "pending";
  const privacyAccepted =
    privacy.state === "accepted" &&
    privacy.policyVersion === privacy.currentVersion &&
    privacy.deletionState === "active";
  const privacyDisclosureReady = Boolean(privacy.legalOperatorName && privacy.privacyContactEmail);

  return (
    <>
      <LegacyDomainRedirect />
      <main className="auth-shell">
        <section className="card account-card" aria-labelledby="account-title">
        <Link className="auth-back" href="/" aria-label="返回个人日程">←</Link>
        <h1 id="account-title">账户管理</h1>
        {session ? <p>{session.user.name} · {session.user.email}</p> : null}
        {message ? <p className="auth-message" aria-live="polite">{message}</p> : null}

        {session ? (
          <>
            <section className="account-section" aria-label="登录方式">
              <p className="account-section-title">登录方式</p>
              <div className="account-methods" aria-label="已连接的登录方式">
                {accounts.length ? accounts.map((account) => <span key={account.id}>{account.providerId === "credential" ? "邮箱和密码" : "Google"}</span>) : <span>邮箱和密码</span>}
              </div>
              <button type="button" className="auth-google" onClick={linkGoogle} disabled={isBusy}>连接 Google</button>
              <button type="button" className="auth-google" onClick={() => void signOut()} disabled={isBusy}>退出登录</button>
              <p className="account-note">Google 只会在你主动点击连接后绑定。至少会保留一种可用登录方式。</p>
            </section>

            <section className="account-section" aria-label="同步状态">
              <p className="account-section-title">同步状态</p>
              <p className="account-note" aria-live="polite">
                {syncHealth === "checking"
                  ? "正在确认同步服务…"
                  : syncHealth === "ready"
                    ? "同步服务已连接。符合保存条件的记录可以继续同步到其他设备。"
                    : syncHealth === "unavailable"
                      ? "暂时无法确认同步服务。当前设备上的记录不会因此丢失，可稍后重新检查。"
                      : "还未检查同步服务。"}
              </p>
              <button type="button" className="auth-google" onClick={() => void checkSyncHealth()} disabled={syncHealth === "checking"}>
                {syncHealth === "checking" ? "正在检查…" : "检查同步状态"}
              </button>
            </section>

            <section className="account-section" aria-label="数据导出与删除">
              <p className="account-section-title">导出与删除</p>
              <div className="account-actions">
                <button type="button" className="auth-primary-link" onClick={exportAccount} disabled={isBusy}>导出全部账户数据</button>
                {isPendingDelete ? (
                  <>
                    <button type="button" className="auth-primary-link" onClick={confirmDeletion} disabled={isBusy}>确认删除（可恢复）</button>
                    <button type="button" className="auth-google" onClick={undoDeletion} disabled={isBusy}>撤销删除</button>
                  </>
                ) : (
                  <button type="button" className="auth-google" onClick={requestDeletion} disabled={isBusy}>开始删除（支持撤销）</button>
                )}
              </div>
              <p className="account-note">
                当前删除状态：{deletion === "pending" ? "待确认" : "正常"}，恢复口令将在 <strong>{prettyDate(tokenExpiresAt)}</strong> 后失效。
              </p>
              {requiresFreshLogin ? (
                <p className="account-note">
                  为保护账户安全，请先 <Link href="/auth/sign-in">重新登录</Link>，再回到账户页继续删除。
                </p>
              ) : null}
              {exportHash ? <p className="account-note">导出摘要：<code>{exportHash}</code></p> : null}
              {deletionToken ? <p className="account-note">恢复口令（本页暂存）：<code>{deletionToken}</code></p> : null}
              {exported ? (
                <>
                  <p className="account-note">导出内容（示例）：</p>
                  <textarea className="account-textarea" rows={8} readOnly value={exported} />
                </>
              ) : null}
            </section>

            <section className="account-section" aria-label="隐私与跨设备">
              <p className="account-section-title">敏感内容跨设备最小化</p>
              <div className="account-note" role="note" aria-label="敏感跨设备保存隐私说明">
                <p><strong>敏感跨设备保存隐私说明（{privacy.currentVersion}）</strong></p>
                <p>本机记录不会被这项选择阻塞；只有你明确开启后，经期、体重、日记、账单及相关私有图片才会开始新的云端处理，以便你在其他设备继续访问。</p>
                <p>启用后的权威云端数据分别保存在 D1 与私有 R2；ChatGPT Sites 当前无数据驻留保证。数据会保留到你撤回同意或删除账户；你可随时导出全部账户数据、关闭并撤回，或开始可恢复的删除流程。</p>
                <p>本产品不是医疗、诊断、治疗或 PHI 服务，也不面向儿童。运营者：{privacy.legalOperatorName ?? "当前候选尚未配置"}；隐私联系：{privacy.privacyContactEmail ? <a href={`mailto:${privacy.privacyContactEmail}`}>{privacy.privacyContactEmail}</a> : "当前候选尚未配置"}。</p>
              </div>
              <p className="account-note">
                当前策略：{privacyAccepted ? "已开启" : "未开启"}（版本 {privacy.policyVersion ?? privacy.currentVersion}）
              </p>
              <p className="account-note">首次开启前已同意版本：{privacy.policyVersion || "未同意"}，同意时间：{prettyDate(privacy.consentedAt)}。</p>
              {privacy.revokedAt ? <p className="account-note">最近撤回：{prettyDate(privacy.revokedAt)}。</p> : null}
              <div className="account-actions">
                <button type="button" className="auth-primary-link" onClick={() => void setConsent("accepted")} disabled={isBusy || privacyAccepted || !privacyDisclosureReady}>
                  开启敏感跨设备
                </button>
                <button type="button" className="auth-google" onClick={() => void setConsent("revoked")} disabled={isBusy || !privacyAccepted}>
                  关闭并撤回
                </button>
              </div>
              {!privacyDisclosureReady ? <p className="account-note">隐私联系信息尚未配置，当前环境不能开启敏感跨设备保存。</p> : null}
            </section>

            <DeviceHistoryTransferPanel returnTo={returnTo} />
            <LegacyImportPanel />
          </>
        ) : <Link className="auth-primary-link" href="/auth/sign-in">去登录</Link>}
        </section>
      </main>
    </>
  );
}
