"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  authSubmissionPreflight,
  buildAuthRequest,
  readResetToken,
  resolveCaptchaResponse,
  safeAuthFailureMessage,
  SIGN_UP_VERIFICATION_PATH,
  type AuthMode,
  usesTurnstileFor,
} from "./auth-flow";

type TurnstileApi = {
  render(
    container: HTMLElement,
    options: {
      sitekey: string;
      action: string;
      callback(token: string): void;
      "expired-callback"(): void;
      "error-callback"(): void;
    },
  ): string;
  remove(widgetId: string): void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

type AuthFormProps = {
  mode: AuthMode;
  turnstileSiteKey: string | null;
};

const initialMessages: Record<AuthMode, string> = {
  "sign-in": "登录后，换设备也能接着用。",
  "sign-up": "注册后请完成邮箱验证，再开始记录。",
  "forgot-password": "我们会用相同提示保护你的账户信息。",
  "reset-password": "设置一个至少 12 位的新密码。",
  "verify-email": "请打开验证邮件中的链接；未收到时可重新发送。",
};

function titleFor(mode: AuthMode): string {
  return {
    "sign-in": "欢迎回来",
    "sign-up": "创建你的账户",
    "forgot-password": "找回密码",
    "reset-password": "设置新密码",
    "verify-email": "验证邮箱",
  }[mode];
}

function linkFor(mode: AuthMode): { href: string; label: string } {
  if (mode === "sign-in") return { href: "/auth/sign-up", label: "还没有账户？去注册" };
  if (mode === "sign-up") return { href: "/auth/sign-in", label: "已有账户？去登录" };
  return { href: "/auth/sign-in", label: "返回登录" };
}

export function AuthForm({ mode, turnstileSiteKey }: AuthFormProps) {
  const turnstileContainer = useRef<HTMLDivElement>(null);
  const [fetchedSiteKey, setFetchedSiteKey] = useState<string | null>(null);
  const siteKey = turnstileSiteKey ?? fetchedSiteKey;
  const [turnstileToken, setTurnstileToken] = useState("");
  const [message, setMessage] = useState(initialMessages[mode]);
  const [submitting, setSubmitting] = useState(false);
  const searchParams = useSearchParams();
  const usesTurnstile = usesTurnstileFor(mode);
  const showVerifiedSignInMessage = mode === "sign-in" && searchParams.get("verified") === "1" && message === initialMessages["sign-in"];
  const displayedMessage = showVerifiedSignInMessage ? "邮箱已验证，请登录。" : message;

  useEffect(() => {
    if (turnstileSiteKey) return;
    let active = true;
    void fetch("/api/auth/public-config", { credentials: "same-origin" })
      .then((response) => (response.ok ? response.json() : null))
      .then((value: unknown) => {
        if (
          active &&
          value &&
          typeof value === "object" &&
          typeof (value as { turnstileSiteKey?: unknown }).turnstileSiteKey === "string"
        ) {
          setFetchedSiteKey((value as { turnstileSiteKey: string }).turnstileSiteKey);
        }
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [turnstileSiteKey]);

  useEffect(() => {
    if (!usesTurnstile || !siteKey || !turnstileContainer.current) return;

    let widgetId: string | undefined;
    let cancelled = false;
    const mount = () => {
      if (cancelled || !window.turnstile || !turnstileContainer.current) return;
      widgetId = window.turnstile.render(turnstileContainer.current, {
        sitekey: siteKey,
        action: "workbench_auth",
        callback: setTurnstileToken,
        "expired-callback": () => setTurnstileToken(""),
        "error-callback": () => setTurnstileToken(""),
      });
    };

    const existing = document.querySelector<HTMLScriptElement>('script[data-workbench-turnstile="true"]');
    if (window.turnstile) {
      mount();
    } else if (existing) {
      existing.addEventListener("load", mount, { once: true });
    } else {
      const script = document.createElement("script");
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      script.async = true;
      script.defer = true;
      script.dataset.workbenchTurnstile = "true";
      script.addEventListener("load", mount, { once: true });
      document.head.appendChild(script);
    }

    return () => {
      cancelled = true;
      if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
    };
  }, [siteKey, usesTurnstile]);

  async function submitGoogle(): Promise<void> {
    setSubmitting(true);
    setMessage("");
    try {
      const response = await fetch("/api/auth/sign-in/social", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ provider: "google", callbackURL: "/" }),
      });
      const payload = (await response.json().catch(() => null)) as { url?: unknown } | null;
      if (response.ok && typeof payload?.url === "string") {
        window.location.assign(payload.url);
        return;
      }
      setMessage(safeAuthFailureMessage(response.status, "sign-in"));
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitForm(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const resetToken = readResetToken(window.location.search);
    const preflightMessage = authSubmissionPreflight(mode, resetToken);
    if (preflightMessage) {
      setMessage(preflightMessage);
      return;
    }
    const renderedTurnstileToken = usesTurnstile
      ? document.querySelector<HTMLInputElement>('input[name="cf-turnstile-response"]')?.value ?? ""
      : "";
    const captchaResponse = resolveCaptchaResponse(turnstileToken, renderedTurnstileToken);
    if (usesTurnstile && siteKey && !captchaResponse) {
      setMessage("请完成验证后继续。");
      return;
    }

    const fields = new FormData(event.currentTarget);
    const email = String(fields.get("email") ?? "").trim();
    const password = String(fields.get("password") ?? "");
    const name = String(fields.get("name") ?? "").trim();
    const request = buildAuthRequest(mode, {
      email,
      password,
      name,
      captchaResponse,
      resetToken,
    });

    setSubmitting(true);
    setMessage("");
    try {
      const response = await fetch(request.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...request.headers },
        credentials: "same-origin",
        body: JSON.stringify(request.body),
      });
      if (!response.ok) {
        setMessage(safeAuthFailureMessage(response.status, mode));
        return;
      }
      if (mode === "sign-in") {
        window.location.assign("/");
        return;
      }
      if (mode === "sign-up") {
        window.location.assign(SIGN_UP_VERIFICATION_PATH);
        return;
      }
      if (mode === "forgot-password") setMessage("如果该邮箱可以接收重设邮件，我们已发送下一步说明。");
      if (mode === "reset-password") setMessage("密码已更新，请重新登录。");
      if (mode === "verify-email") setMessage("如果该邮箱可以接收验证邮件，我们已发送下一步说明。");
    } catch {
      setMessage("服务暂时不可用，请稍后再试。");
    } finally {
      setSubmitting(false);
    }
  }

  const link = linkFor(mode);
  const showPassword = mode === "sign-in" || mode === "sign-up" || mode === "reset-password";

  return (
    <main className="auth-shell">
      <section className="card auth-card auth-card-expanded" aria-labelledby="auth-title">
        <Link className="auth-back" href="/" aria-label="返回工作台">←</Link>
        <h1 id="auth-title">{titleFor(mode)}</h1>
        <p className="auth-message" aria-live="polite">{displayedMessage}</p>
        <form className="auth-form" onSubmit={submitForm}>
          {mode === "sign-up" ? (
            <label><span>名字</span><input name="name" autoComplete="name" maxLength={80} required /></label>
          ) : null}
          {mode !== "reset-password" ? (
            <label><span>邮箱</span><input name="email" type="email" autoComplete="email" required /></label>
          ) : null}
          {showPassword ? (
            <label>
              <span>{mode === "reset-password" ? "新密码" : "密码"}</span>
              <input
                name="password"
                type="password"
                autoComplete={mode === "reset-password" ? "new-password" : "current-password"}
                minLength={12}
                maxLength={128}
                required
              />
            </label>
          ) : null}
          {usesTurnstile ? <div className="turnstile-slot" ref={turnstileContainer} /> : null}
          <button type="submit" className="auth-submit" disabled={submitting}>
            {submitting ? "请稍候…" : mode === "sign-up" ? "注册" : mode === "forgot-password" ? "发送说明" : mode === "reset-password" ? "更新密码" : mode === "verify-email" ? "重新发送验证邮件" : "登录"}
          </button>
        </form>
        {mode === "verify-email" ? (
          <Link className="auth-primary-link" href="/auth/sign-in">返回登录</Link>
        ) : (
          <Link className="auth-secondary-link" href={link.href}>{link.label}</Link>
        )}
        {mode === "sign-in" || mode === "sign-up" ? (
          <button type="button" className="auth-google" onClick={submitGoogle} disabled={submitting}>使用 Google 继续</button>
        ) : null}
        {mode === "sign-in" ? <Link className="auth-secondary-link" href="/auth/forgot-password">忘记密码？</Link> : null}
      </section>
    </main>
  );
}
