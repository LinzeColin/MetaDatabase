export type AuthMode = "sign-in" | "sign-up" | "forgot-password" | "reset-password" | "verify-email";

export const SIGN_UP_VERIFICATION_PATH = "/auth/verify-email";
export const VERIFIED_LOGIN_PATH = "/auth/sign-in?verified=1";

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
          callbackURL: "/",
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
