export type AuthMode = "sign-in" | "sign-up" | "forgot-password" | "reset-password" | "verify-email";
export type CaptchaReadiness = "loading" | "ready" | "unavailable";

export const SIGN_UP_VERIFICATION_PATH = "/auth/verify-email";
export const VERIFIED_LOGIN_PATH = "/auth/sign-in?verified=1";
export const AUTHENTICATED_HOME_PATH = "/?view=home";

export type AuthFormValues = {
  email: string;
  password: string;
  name: string;
  captchaResponse: string;
  resetToken: string;
};

export type AuthRequest = {
  endpoint: string;
  body: Record<string, string>;
  headers?: Record<string, string>;
};

export function usesTurnstileFor(mode: AuthMode): boolean {
  return mode === "sign-in" || mode === "sign-up" || mode === "forgot-password";
}

/**
 * Managed Turnstile can populate its rendered hidden input just before React
 * processes the callback. Prefer the callback state, then use that same
 * rendered response so a valid token is never discarded by a timing race.
 */
export function resolveCaptchaResponse(callbackToken: string, renderedToken: string): string {
  return callbackToken.trim() || renderedToken.trim();
}

/**
 * Do not send an authentication request until the public Turnstile
 * configuration has loaded. Sending the normal form first would make the
 * provider reject an otherwise valid form as a missing CAPTCHA response,
 * which appears to a visitor as an inert button.
 */
export function captchaSubmissionPreflight(
  mode: AuthMode,
  readiness: CaptchaReadiness,
  captchaResponse: string,
): string | null {
  if (!usesTurnstileFor(mode)) return null;
  if (readiness === "loading") return "正在加载安全验证，请稍候…";
  if (readiness === "unavailable") return "安全验证暂不可用，请检查网络后重试。";
  if (!captchaResponse.trim()) return "请完成验证后继续。";
  return null;
}

/**
 * Keeps authentication errors useful without exposing whether an account or
 * message exists. A rate-limit response must not masquerade as either invalid
 * credentials or a successfully sent email.
 */
export function safeAuthFailureMessage(status: number, mode: AuthMode): string {
  if (status === 429) return "操作次数较多，请稍后再试。";
  if (status === 503 || status >= 500) return "服务暂时不可用，请稍后再试。";
  if (mode === "forgot-password") return "如果该邮箱可以接收重设邮件，我们已发送下一步说明。";
  if (mode === "verify-email") return "如果该邮箱可以接收验证邮件，我们已发送下一步说明。";
  if (mode === "sign-up") return "请检查填写内容；若账户已存在，请直接登录或完成邮箱验证。";
  if (mode === "sign-in") return "账号或密码不正确，或邮箱尚未完成验证。";
  return "链接无效或已过期，请重新发起操作。";
}

export function readResetToken(search: string): string {
  return new URLSearchParams(search).get("token")?.trim() ?? "";
}

/**
 * Avoid a misleading network submission when a reset page was opened without
 * the one-time token that the server requires. A non-empty token still goes to
 * the server, which remains the sole authority for expiry and validity.
 */
export function authSubmissionPreflight(mode: AuthMode, resetToken: string): string | null {
  if (mode === "reset-password" && !resetToken) return safeAuthFailureMessage(400, mode);
  return null;
}

function captchaHeaders(response: string): Record<string, string> | undefined {
  const token = response.trim();
  return token ? { "x-captcha-response": token } : undefined;
}

/**
 * Keeps every browser-auth request on an explicit, same-origin Better Auth
 * endpoint. Callback paths are constants so an untrusted query cannot become
 * an open redirect or leak an email address through the URL.
 */
export function buildAuthRequest(mode: AuthMode, values: AuthFormValues): AuthRequest {
  switch (mode) {
    case "sign-in":
      return {
        endpoint: "/api/auth/sign-in/email",
        headers: captchaHeaders(values.captchaResponse),
        body: {
          email: values.email,
          password: values.password,
          callbackURL: AUTHENTICATED_HOME_PATH,
        },
      };
    case "sign-up":
      return {
        endpoint: "/api/auth/sign-up/email",
        headers: captchaHeaders(values.captchaResponse),
        body: {
          name: values.name,
          email: values.email,
          password: values.password,
          callbackURL: VERIFIED_LOGIN_PATH,
        },
      };
    case "forgot-password":
      return {
        endpoint: "/api/auth/request-password-reset",
        headers: captchaHeaders(values.captchaResponse),
        body: {
          email: values.email,
          redirectTo: "/auth/reset-password",
        },
      };
    case "reset-password":
      return {
        endpoint: "/api/auth/reset-password",
        body: { newPassword: values.password, token: values.resetToken },
      };
    case "verify-email":
      return {
        endpoint: "/api/auth/send-verification-email",
        body: { email: values.email, callbackURL: VERIFIED_LOGIN_PATH },
      };
  }
}
