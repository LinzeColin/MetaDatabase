"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  AUTHENTICATED_HOME_PATH,
  authenticatedLocationAfterEmailSignIn,
  authSubmissionPreflight,
  buildAuthRequest,
  captchaSubmissionPreflight,
  readResetToken,
  resolveCaptchaResponse,
  safeAuthFailureMessage,
  SIGN_UP_VERIFICATION_PATH,
  type CaptchaReadiness,
  type AuthMode,
  usesTurnstileFor,
} from "./auth-flow";
import { markAuthReturnRecovery } from "./auth-return-recovery";
import { GoogleIdentityButton } from "./google-identity-button";
import { requestWithTimeout } from "../../_components/workbench/request-timeout";

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
  googleClientId?: string | null;
};

const CAPTCHA_SCRIPT_LOAD_TIMEOUT_MS = 15_000;
const CAPTCHA_UNAVAILABLE_MESSAGE = "安全验证暂不可用，请检查网络后重试。";

const initialMessages: Record<AuthMode, string> = {
  "sign-in": "登录后，换设备也能接着用。",
  "sign-up": "注册后请完成邮箱验证，再开始记录。",
  "forgot-password": "我们会用相同提示保护你的账户信息。",
  "reset-password": "设置一个至少 12 位的新密码。",
  "verify-email": "请打开验证邮件中的链接；未收到时可重新发送。",
};

function subscribeToHydration() {
  return () => {};
}

function hydratedSnapshot() {
  return true;
}

function serverSnapshot() {
  return false;
}

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

export function AuthForm({ mode, turnstileSiteKey, googleClientId = null }: AuthFormProps) {
  const usesTurnstile = usesTurnstileFor(mode);
  const turnstileContainer = useRef<HTMLDivElement>(null);
  const [fetchedSiteKey, setFetchedSiteKey] = useState<string | null>(null);
  const [captchaReadiness, setCaptchaReadiness] = useState<CaptchaReadiness>(
    () => (usesTurnstile ? "loading" : "ready"),
  );
  const [captchaRetryNonce, setCaptchaRetryNonce] = useState(0);
  // A server-supplied site key means the widget may begin mounting immediately,
  // not that the browser can necessarily reach the verification service.
  const effectiveCaptchaReadiness: CaptchaReadiness = usesTurnstile ? captchaReadiness : "ready";
  const siteKey = turnstileSiteKey ?? fetchedSiteKey;
  const [turnstileToken, setTurnstileToken] = useState("");
  const [message, setMessage] = useState(initialMessages[mode]);
  const [submitting, setSubmitting] = useState(false);
  const interactive = useSyncExternalStore(subscribeToHydration, hydratedSnapshot, serverSnapshot);
  const searchParams = useSearchParams();
  const showVerifiedSignInMessage = mode === "sign-in" && searchParams.get("verified") === "1" && message === initialMessages["sign-in"];
  const showSignedOutMessage = mode === "sign-in" && searchParams.get("signed_out") === "1" && message === initialMessages["sign-in"];
  const showServerStartFailure = mode === "sign-in" && searchParams.get("auth_error") === "1" && message === initialMessages["sign-in"];
  const continueGoogleLinkAfterEmailSignIn = mode === "sign-in" && searchParams.get("link_google") === "1";
  const displayedMessage = showVerifiedSignInMessage
    ? "邮箱已验证，请登录。"
    : showSignedOutMessage
      ? "已退出登录。"
      : showServerStartFailure
        ? "登录入口暂时不可用，请稍后重试。"
      : continueGoogleLinkAfterEmailSignIn && message === initialMessages["sign-in"]
        ? "先使用邮箱和密码确认已有账户；登录后会继续完成 Google 连接。"
      : !interactive
        ? "正在准备登录…"
        : message;

  useEffect(() => {
    if (!usesTurnstile || turnstileSiteKey || fetchedSiteKey) return;
    let active = true;
    void requestWithTimeout("/api/auth/public-config", { credentials: "same-origin" })
      .then((response) => (response.ok ? response.json() : null))
      .then((value: unknown) => {
        if (!active) return;
        if (
          value &&
          typeof value === "object" &&
          typeof (value as { turnstileSiteKey?: unknown }).turnstileSiteKey === "string"
        ) {
          const nextKey = (value as { turnstileSiteKey: string }).turnstileSiteKey.trim();
          if (nextKey) {
            setFetchedSiteKey(nextKey);
            return;
          }
        }
        setCaptchaReadiness("unavailable");
      })
      .catch(() => {
        if (active) setCaptchaReadiness("unavailable");
      });
    return () => { active = false; };
  }, [captchaRetryNonce, fetchedSiteKey, turnstileSiteKey, usesTurnstile]);

  useEffect(() => {
    if (!usesTurnstile || !siteKey || !turnstileContainer.current) return;

    let widgetId: string | undefined;
    let scriptLoadTimeout: number | undefined;
    let scriptElement: HTMLScriptElement | null = null;
    let cancelled = false;
    const clearScriptLoadTimeout = () => {
      if (scriptLoadTimeout === undefined) return;
      window.clearTimeout(scriptLoadTimeout);
      scriptLoadTimeout = undefined;
    };
    const markUnavailable = () => {
      if (cancelled) return;
      clearScriptLoadTimeout();
      setTurnstileToken("");
      setCaptchaReadiness("unavailable");
    };
    const mount = () => {
      if (cancelled || !window.turnstile || !turnstileContainer.current) return;
      clearScriptLoadTimeout();
      // A rendered Turnstile challenge can legitimately wait for a person to
      // complete it. Only a missing script is a load failure; never turn an
      // already-visible challenge into "unavailable" after an arbitrary timer.
      setCaptchaReadiness("challenge");
      try {
        widgetId = window.turnstile.render(turnstileContainer.current, {
          sitekey: siteKey,
          action: "workbench_auth",
          callback: (token) => {
            if (cancelled) return;
            setTurnstileToken(token);
            setCaptchaReadiness("ready");
          },
          "expired-callback": () => {
            setTurnstileToken("");
            setCaptchaReadiness("challenge");
          },
          "error-callback": markUnavailable,
        });
      } catch {
        markUnavailable();
      }
    };

    const waitForScript = (script: HTMLScriptElement) => {
      scriptElement = script;
      scriptLoadTimeout = window.setTimeout(markUnavailable, CAPTCHA_SCRIPT_LOAD_TIMEOUT_MS);
      script.addEventListener("load", mount, { once: true });
      script.addEventListener("error", markUnavailable, { once: true });
    };

    const existing = document.querySelector<HTMLScriptElement>('script[data-workbench-turnstile="true"]');
    if (window.turnstile) {
      mount();
    } else if (existing) {
      waitForScript(existing);
    } else {
      const script = document.createElement("script");
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      script.async = true;
      script.defer = true;
      script.dataset.workbenchTurnstile = "true";
      waitForScript(script);
      document.head.appendChild(script);
    }

    return () => {
      cancelled = true;
      clearScriptLoadTimeout();
      scriptElement?.removeEventListener("load", mount);
      scriptElement?.removeEventListener("error", markUnavailable);
      if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
    };
  }, [captchaRetryNonce, siteKey, usesTurnstile]);

  function retryCaptcha(): void {
    setTurnstileToken("");
    setCaptchaReadiness("loading");
    // A failed external script is not reloadable. Remove only that failed
    // element; a loaded Turnstile runtime is safely remounted by the effect.
    if (!window.turnstile) {
      document.querySelector<HTMLScriptElement>('script[data-workbench-turnstile="true"]')?.remove();
    }
    setCaptchaRetryNonce((attempt) => attempt + 1);
  }

  function beginGoogleSignIn(): void {
    setSubmitting(true);
    setMessage("正在完成 Google 登录…");
  }

  function completeGoogleSignIn(): void {
    markAuthReturnRecovery();
    window.location.assign(AUTHENTICATED_HOME_PATH);
  }

  function failGoogleSignIn(nextMessage: string): void {
    setSubmitting(false);
    setMessage(nextMessage);
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
    const captchaPreflightMessage = captchaSubmissionPreflight(mode, effectiveCaptchaReadiness, captchaResponse);
    if (captchaPreflightMessage) {
      setMessage(captchaPreflightMessage);
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
      const response = await requestWithTimeout(request.endpoint, {
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
        markAuthReturnRecovery();
        window.location.assign(authenticatedLocationAfterEmailSignIn(continueGoogleLinkAfterEmailSignIn));
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
        <Link className="auth-back" href="/" aria-label="返回个人日程">←</Link>
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
          {usesTurnstile && effectiveCaptchaReadiness === "loading" ? (
            <p className="auth-captcha-message" role="status">正在准备安全验证，请稍候…</p>
          ) : null}
          {usesTurnstile && effectiveCaptchaReadiness === "challenge" ? (
            <p className="auth-captcha-message" role="status">请完成安全验证后继续。</p>
          ) : null}
          {usesTurnstile && effectiveCaptchaReadiness === "unavailable" ? (
            <>
              {message !== CAPTCHA_UNAVAILABLE_MESSAGE ? <p className="auth-captcha-message" role="status">{CAPTCHA_UNAVAILABLE_MESSAGE}</p> : null}
              <button type="button" className="auth-google" onClick={retryCaptcha} disabled={!interactive || submitting}>
                重试安全验证
              </button>
            </>
          ) : null}
          <button type="submit" className="auth-submit" disabled={!interactive || submitting}>
            {submitting ? "请稍候…" : mode === "sign-up" ? "注册" : mode === "forgot-password" ? "发送说明" : mode === "reset-password" ? "更新密码" : mode === "verify-email" ? "重新发送验证邮件" : "登录"}
          </button>
        </form>
        {mode === "verify-email" ? (
          <Link className="auth-primary-link" href="/auth/sign-in">返回登录</Link>
        ) : (
          <Link className="auth-secondary-link" href={link.href}>{link.label}</Link>
        )}
        {mode === "sign-in" || mode === "sign-up" ? (
          <GoogleIdentityButton
            clientId={googleClientId}
            disabled={!interactive || submitting}
            callbackURL={AUTHENTICATED_HOME_PATH}
            fallbackHref="/auth/google"
            onStart={beginGoogleSignIn}
            onSuccess={completeGoogleSignIn}
            onFailure={failGoogleSignIn}
            onFallback={markAuthReturnRecovery}
          />
        ) : null}
        {mode === "sign-in" ? <Link className="auth-secondary-link" href="/auth/forgot-password">忘记密码？</Link> : null}
      </section>
    </main>
  );
}
