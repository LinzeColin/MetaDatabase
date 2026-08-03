/**
 * Logical runtime bindings declared in .openai/hosting.json.
 * Sites provisions the concrete resources; source code uses only these names.
 */
declare namespace Cloudflare {
  interface Env {
    DB: D1Database;
    FILES: R2Bucket;
  }
}
