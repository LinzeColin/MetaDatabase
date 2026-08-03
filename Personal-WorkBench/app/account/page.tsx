"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Account = { id: string; providerId: string };
type Session = { user: { name: string; email: string; emailVerified: boolean } } | null;

export default function AccountPage() {
  const [session, setSession] = useState<Session>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [message, setMessage] = useState("正在确认账户状态…");

  useEffect(() => {
    async function load() {
      try {
        const sessionResponse = await fetch("/api/auth/get-session", { credentials: "same-origin" });
        if (!sessionResponse.ok) {
          setMessage("请先登录后再管理账户。");
          return;
        }
        const nextSession = (await sessionResponse.json()) as Session;
        if (!nextSession?.user?.emailVerified) {
          setMessage("请先完成邮箱验证。");
          return;
        }
        setSession(nextSession);
        const accountResponse = await fetch("/api/auth/list-accounts", { credentials: "same-origin" });
        if (accountResponse.ok) setAccounts((await accountResponse.json()) as Account[]);
        setMessage("");
      } catch {
        setMessage("服务暂时不可用，请稍后再试。");
      }
    }
    void load();
  }, []);

  async function linkGoogle() {
    setMessage("");
    try {
      const response = await fetch("/api/auth/link-social", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ provider: "google", callbackURL: "/account" }),
      });
      const result = (await response.json().catch(() => null)) as { url?: unknown } | null;
      if (response.ok && typeof result?.url === "string") {
        window.location.assign(result.url);
        return;
      }
      setMessage("暂时无法连接 Google，请稍后再试。");
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    }
  }

  return (
    <main className="auth-shell">
      <section className="card account-card" aria-labelledby="account-title">
        <Link className="auth-back" href="/" aria-label="返回工作台">←</Link>
        <h1 id="account-title">账户与登录方式</h1>
        {session ? <p>{session.user.name} · {session.user.email}</p> : null}
        {message ? <p className="auth-message" aria-live="polite">{message}</p> : null}
        {session ? (
          <>
            <div className="account-methods" aria-label="已连接的登录方式">
              {accounts.length ? accounts.map((account) => <span key={account.id}>{account.providerId === "credential" ? "邮箱和密码" : "Google"}</span>) : <span>邮箱和密码</span>}
            </div>
            <button type="button" className="auth-google" onClick={linkGoogle}>连接 Google</button>
            <p className="account-note">Google 只会在你主动点击连接后绑定。至少会保留一种可用登录方式。</p>
          </>
        ) : <Link className="auth-primary-link" href="/auth/sign-in">去登录</Link>}
      </section>
    </main>
  );
}
