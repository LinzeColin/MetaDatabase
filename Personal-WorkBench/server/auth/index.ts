import { drizzleAdapter } from "@better-auth/drizzle-adapter";
import { drizzle } from "drizzle-orm/d1";
import { betterAuth } from "better-auth";
import { captcha } from "better-auth/plugins";
import { authSchema } from "@/db/schema";
import {
  createMailPort,
  passwordResetMail,
  verificationMail,
} from "./mail";
import {
  AuthRuntimeNotReadyError,
  getAuthRuntimeMissingCategories,
  readAuthRuntimeConfig,
  type AuthRuntimeEnv,
} from "./runtime";
import { allowedTurnstileHostnames, expectedTurnstileAction } from "./turnstile";

export { AuthRuntimeNotReadyError, getPublicAuthPageConfig } from "./runtime";
export type { AuthRuntimeEnv } from "./runtime";

/** Google only grants the tenant data path when its signed claim is strictly true. */
export function isVerifiedGoogleEmailClaim(profile: { email_verified?: unknown }): boolean {
  return profile.email_verified === true;
}

/**
 * Constructs auth only for a fully configured runtime. This prevents the
 * library's development fallback secret from ever being used in this product.
 */
export function createAuth(env: AuthRuntimeEnv) {
  const config = readAuthRuntimeConfig(env);
  if (!config) throw new AuthRuntimeNotReadyError(getAuthRuntimeMissingCategories(env));

  const db = drizzle(config.db, { schema: authSchema });
  const mail = createMailPort({
    provider: config.mailProvider,
    apiKey: config.mailApiKey,
    from: config.fromEmail,
  });

  return betterAuth({
    appName: "个人日程",
    database: drizzleAdapter(db, {
      provider: "sqlite",
      schema: authSchema,
      transaction: false,
    }),
    secret: config.authSecret,
    baseURL: {
      allowedHosts: config.trustedOrigins.map((origin) => new URL(origin).host),
      fallback: config.appOrigin,
    },
    basePath: "/api/auth",
    trustedOrigins: config.trustedOrigins,
    emailAndPassword: {
      enabled: true,
      requireEmailVerification: true,
      minPasswordLength: 12,
      maxPasswordLength: 128,
      autoSignIn: false,
      revokeSessionsOnPasswordReset: true,
      async sendResetPassword({ user, url }) {
        await mail.send(passwordResetMail(user.email, url));
      },
    },
    emailVerification: {
      sendOnSignUp: true,
      sendOnSignIn: true,
      autoSignInAfterVerification: false,
      expiresIn: 30 * 60,
      async sendVerificationEmail({ user, url }) {
        await mail.send(verificationMail(user.email, url));
      },
    },
    socialProviders: {
      google: {
        clientId: config.googleClientId,
        clientSecret: config.googleClientSecret,
        scope: ["openid", "email", "profile"],
        prompt: "select_account",
        mapProfileToUser(profile) {
          return { emailVerified: isVerifiedGoogleEmailClaim(profile) };
        },
      },
    },
    account: {
      accountLinking: {
        enabled: true,
        disableImplicitLinking: true,
        allowDifferentEmails: false,
        allowUnlinkingAll: false,
        updateUserInfoOnLink: false,
      },
    },
    session: {
      expiresIn: 30 * 24 * 60 * 60,
      updateAge: 24 * 60 * 60,
      freshAge: 10 * 60,
    },
    rateLimit: {
      enabled: true,
      storage: "database",
      modelName: "rateLimit",
      window: 60,
      max: 100,
      customRules: {
        "/sign-up/email": { window: 60 * 60, max: 8 },
        "/sign-in/email": { window: 15 * 60, max: 12 },
        "/request-password-reset": { window: 60 * 60, max: 6 },
        "/send-verification-email": { window: 60 * 60, max: 6 },
      },
    },
    advanced: {
      useSecureCookies: true,
      cookiePrefix: "hcl-workbench",
      defaultCookieAttributes: {
        httpOnly: true,
        secure: true,
        sameSite: "lax",
        path: "/",
      },
      ipAddress: {
        ipAddressHeaders: ["cf-connecting-ip"],
      },
    },
    plugins: [
      captcha({
        provider: "cloudflare-turnstile",
        secretKey: config.turnstileSecretKey,
        endpoints: [
          "/sign-up/email",
          "/sign-in/email",
          "/request-password-reset",
        ],
        expectedAction: expectedTurnstileAction(config.turnstileSecretKey, config.trustedOrigins),
        allowedHostnames: allowedTurnstileHostnames(config.turnstileSecretKey, config.trustedOrigins),
      }),
    ],
  });
}
