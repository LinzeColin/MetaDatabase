"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { requestWithTimeout } from "../../_components/workbench/request-timeout";

const GOOGLE_IDENTITY_SCRIPT_SRC = "https://accounts.google.com/gsi/client";
const GOOGLE_IDENTITY_SCRIPT_LOAD_TIMEOUT_MS = 15_000;

type GoogleCredentialResponse = {
  credential?: unknown;
};

type GoogleIdentityApi = {
  initialize(options: {
    client_id: string;
    callback(response: GoogleCredentialResponse): void;
    auto_select: boolean;
    use_fedcm_for_button: boolean;
  }): void;
  renderButton(
    container: HTMLElement,
    options: {
      type: "standard";
      theme: "outline";
      size: "large";
      text: "continue_with";
      shape: "rectangular";
      width: number;
      locale: "zh-CN";
    },
  ): void;
};

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: GoogleIdentityApi;
      };
    };
  }
}

type GoogleIdentityButtonProps = {
  clientId: string | null;
  disabled: boolean;
  callbackURL: string;
  autoStartFallback?: boolean;
  onStart(): void;
  onSuccess(): void;
  onFailure(message: string): void;
  onFallback(): void;
};

type Availability = "loading" | "ready" | "unavailable";

function credentialFrom(response: GoogleCredentialResponse): string {
  return typeof response.credential === "string" ? response.credential.trim() : "";
}

function authorizationUrlFrom(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const rawUrl = (value as { url?: unknown }).url;
  if (typeof rawUrl !== "string") return null;
  try {
    const url = new URL(rawUrl);
    return url.protocol === "https:" && url.hostname === "accounts.google.com" ? url.toString() : null;
  } catch {
    return null;
  }
}

/**
 * Uses Google's supported browser identity credential exchange. Its server
 * verification stays on Better Auth's existing Google provider route, so a
 * browser never receives a secret and the established account-linking rules
 * remain authoritative.
 */
export function GoogleIdentityButton({
  clientId,
  disabled,
  callbackURL,
  autoStartFallback = false,
  onStart,
  onSuccess,
  onFailure,
  onFallback,
}: GoogleIdentityButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const fallbackStartedRef = useRef(false);
  const callbacksRef = useRef({ callbackURL, onStart, onSuccess, onFailure, onFallback });
  const [availability, setAvailability] = useState<Availability>(clientId ? "loading" : "unavailable");

  useEffect(() => {
    callbacksRef.current = { callbackURL, onStart, onSuccess, onFailure, onFallback };
  }, [callbackURL, onFailure, onFallback, onStart, onSuccess]);

  useEffect(() => {
    const container = containerRef.current;
    if (!clientId || !container) {
      setAvailability("unavailable");
      return;
    }

    let active = true;
    let loadTimeout: number | undefined;
    let loadedScript: HTMLScriptElement | null = null;

    const clearLoadTimeout = () => {
      if (loadTimeout === undefined) return;
      window.clearTimeout(loadTimeout);
      loadTimeout = undefined;
    };
    const unavailable = () => {
      if (!active) return;
      clearLoadTimeout();
      setAvailability("unavailable");
      callbacksRef.current.onFailure("Google 登录服务暂时不可用，请稍后重试，或使用邮箱和密码登录。");
    };
    const submitCredential = async (credential: string) => {
      if (!credential) {
        callbacksRef.current.onFailure("Google 没有返回可用的登录凭证，请重新选择账号。");
        return;
      }
      callbacksRef.current.onStart();
      try {
        const response = await requestWithTimeout("/api/auth/sign-in/social", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            provider: "google",
            idToken: { token: credential },
            callbackURL: callbacksRef.current.callbackURL,
          }),
        });
        if (!response.ok) {
          callbacksRef.current.onFailure("Google 登录没有完成，请重新选择账号或使用邮箱和密码登录。");
          return;
        }
        callbacksRef.current.onSuccess();
      } catch {
        callbacksRef.current.onFailure("Google 登录服务暂时不可用，请稍后重试，或使用邮箱和密码登录。");
      }
    };
    const render = () => {
      const identity = window.google?.accounts?.id;
      if (!identity) {
        unavailable();
        return;
      }
      try {
        identity.initialize({
          client_id: clientId,
          callback: (response) => { void submitCredential(credentialFrom(response)); },
          auto_select: false,
          use_fedcm_for_button: true,
        });
        container.replaceChildren();
        identity.renderButton(container, {
          type: "standard",
          theme: "outline",
          size: "large",
          text: "continue_with",
          shape: "rectangular",
          width: Math.max(240, Math.floor(container.getBoundingClientRect().width) || 320),
          locale: "zh-CN",
        });
        clearLoadTimeout();
        if (active) setAvailability("ready");
      } catch {
        unavailable();
      }
    };

    const existing = document.querySelector<HTMLScriptElement>('script[data-mydairy-google-identity="true"]');
    if (window.google?.accounts?.id) {
      render();
    } else if (existing) {
      loadedScript = existing;
      existing.addEventListener("load", render, { once: true });
      existing.addEventListener("error", unavailable, { once: true });
    } else {
      const script = document.createElement("script");
      script.src = GOOGLE_IDENTITY_SCRIPT_SRC;
      script.async = true;
      script.dataset.mydairyGoogleIdentity = "true";
      script.addEventListener("load", render, { once: true });
      script.addEventListener("error", unavailable, { once: true });
      loadedScript = script;
      document.head.appendChild(script);
    }
    loadTimeout = window.setTimeout(unavailable, GOOGLE_IDENTITY_SCRIPT_LOAD_TIMEOUT_MS);

    return () => {
      active = false;
      clearLoadTimeout();
      loadedScript?.removeEventListener("load", render);
      loadedScript?.removeEventListener("error", unavailable);
    };
  }, [clientId]);

  const startOAuthFallback = useCallback(async () => {
    if (disabled) return;
    callbacksRef.current.onStart();
    try {
      const response = await requestWithTimeout("/api/auth/sign-in/social", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          provider: "google",
          callbackURL: callbacksRef.current.callbackURL,
        }),
      });
      const authorizationUrl = response.ok ? authorizationUrlFrom(await response.json()) : null;
      if (!authorizationUrl) {
        callbacksRef.current.onFailure("无法启动 Google 授权，请稍后重试，或使用邮箱和密码登录。");
        return;
      }
      callbacksRef.current.onFallback();
      window.location.assign(authorizationUrl);
    } catch {
      callbacksRef.current.onFailure("Google 登录服务暂时不可用，请稍后重试，或使用邮箱和密码登录。");
    }
  }, [disabled]);

  useEffect(() => {
    if (!autoStartFallback || disabled || fallbackStartedRef.current) return;
    fallbackStartedRef.current = true;
    void startOAuthFallback();
  }, [autoStartFallback, disabled, startOAuthFallback]);

  // Server rendering happens before this component can load either React's
  // handlers or Google's identity script. Keep a real link during that whole
  // window, so a visitor can still begin the same server-owned OAuth flow
  // instead of seeing an inert or empty login control. Once GIS is ready it
  // replaces this progressive-enhancement fallback with its native button.
  if (availability !== "ready") {
    return (
      <a className="auth-google" data-google-native-fallback="true" href="/auth/google">
        使用 Google 授权登录
      </a>
    );
  }

  return (
    <div
      className={`auth-google-identity${disabled ? " is-disabled" : ""}`}
      aria-busy={disabled}
      aria-label="使用 Google 继续"
    >
      <div ref={containerRef} />
    </div>
  );
}
