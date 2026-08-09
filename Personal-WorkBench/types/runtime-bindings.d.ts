/**
 * Logical runtime bindings declared in .openai/hosting.json.
 * Sites provisions the concrete resources; source code uses only these names.
 */
declare namespace Cloudflare {
  interface Env {
    DB: D1Database;
    FILES: R2Bucket;
    BETTER_AUTH_SECRET?: string;
    APP_ORIGIN?: string;
    GOOGLE_CLIENT_ID?: string;
    GOOGLE_CLIENT_SECRET?: string;
    RESEND_API_KEY?: string;
    NITROSEND_API_KEY?: string;
    MAIL_PROVIDER?: string;
    AUTH_FROM_EMAIL?: string;
    MAIL_FROM?: string;
    TURNSTILE_SECRET_KEY?: string;
    TURNSTILE_SITE_KEY?: string;
    LEGAL_OPERATOR_NAME?: string;
    PRIVACY_CONTACT_EMAIL?: string;
  }
}
