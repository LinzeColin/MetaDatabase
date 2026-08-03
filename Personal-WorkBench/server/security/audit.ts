type AuditEnv = { DB: D1Database };

/**
 * Security events intentionally carry no request body, email address, object
 * key, or other business content. This keeps auditability separate from PII.
 */
export async function writeRedactedSecurityEvent(
  env: AuditEnv,
  userId: string | null,
  eventType: string,
  outcome: "success" | "rejected" | "failed",
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO security_audit_events
      (id, user_id, event_type, outcome, ip_digest, user_agent_digest, details_json, created_at)
      VALUES (?, ?, ?, ?, NULL, NULL, '{}', ?)`,
  )
    .bind(crypto.randomUUID(), userId, eventType, outcome, Date.now())
    .run();
}
