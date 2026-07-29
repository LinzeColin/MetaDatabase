'use strict';

const FORBIDDEN_KEYS = /(?:wechat[_-]?id|sender(?:[_-]?(?:id|name|raw))?|user[_-]?id|person(?:[_-]?(?:id|name|raw))?|(?:message|prompt|response)(?:$|[_-](?:text|body|content|raw|payload))|api[_-]?key|file[_-]?name|profile(?:$|[_-](?:value|content|raw))|object[_-]?key|(?:access|refresh|session|setup|csrf|auth|bearer|api|id)[_-]?token|token[_-]?(?:value|hash|secret|raw)|secret|email)/i;
const FORBIDDEN_VALUE_PATTERNS = [
  /\bwxid_[A-Za-z0-9_-]{4,}\b/i,
  /\busr_[A-Za-z0-9_-]{20,}\b/,
  /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i,
  /\bBearer\s+[A-Za-z0-9._~+\/-]{12,}\b/i,
  /\bsk-[A-Za-z0-9_-]{16,}\b/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
];

function assertNoSensitiveValues(value, path = '$') {
  if (value === null || value === undefined || typeof value === 'number' || typeof value === 'boolean') return;
  if (typeof value === 'string') {
    if (FORBIDDEN_VALUE_PATTERNS.some((pattern) => pattern.test(value))) {
      throw Object.assign(new Error(`STATUS_VALUE_FORBIDDEN:${path}`), { code: 'STATUS_VALUE_FORBIDDEN' });
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoSensitiveValues(item, `${path}[${index}]`));
    return;
  }
  if (typeof value === 'object') {
    for (const [key, item] of Object.entries(value)) {
      if (FORBIDDEN_KEYS.test(key)) throw Object.assign(new Error(`STATUS_FIELD_FORBIDDEN:${key}`), { code: 'STATUS_FIELD_FORBIDDEN' });
      assertNoSensitiveValues(item, `${path}.${key}`);
    }
  }
}

function buildBusinessMatrix(lines) {
  return lines.map((line) => {
    assertNoSensitiveValues(line);
    return {
      business_line: line.business_line,
      stage: line.stage,
      state: line.state,
      upstream: line.upstream || [],
      downstream: line.downstream || [],
      slo: line.slo || null,
      queue_depth: Number(line.queue_depth || 0),
      oldest_job_seconds: Number(line.oldest_job_seconds || 0),
      error_rate: Number(line.error_rate || 0),
      last_success_at: line.last_success_at || null,
      last_recovery_at: line.last_recovery_at || null,
      release: line.release || null,
      rollback_release: line.rollback_release || null,
      reason_code: line.reason_code || null,
    };
  });
}

module.exports = { buildBusinessMatrix, assertNoSensitiveValues, FORBIDDEN_KEYS, FORBIDDEN_VALUE_PATTERNS };
