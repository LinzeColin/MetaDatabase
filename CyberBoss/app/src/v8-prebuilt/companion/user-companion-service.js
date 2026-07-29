'use strict';

const KINDS = Object.freeze(['timeline', 'diary', 'reminder']);

function assertContext(context) {
  if (!context || typeof context.requireActive !== 'function') throw new TypeError('active UserContext required');
  context.requireActive();
  return context;
}

class UserCompanionService {
  constructor({ repository, ownerToolHandlers = {} }) {
    if (!repository || typeof repository.append !== 'function' || typeof repository.list !== 'function') {
      throw new TypeError('repository append/list required');
    }
    this.repository = repository;
    this.ownerToolHandlers = Object.freeze({ ...ownerToolHandlers });
  }

  async append(context, { kind, entryId, payload }) {
    assertContext(context);
    if (!KINDS.includes(kind)) throw new TypeError('unsupported companion kind');
    if (!/^[A-Za-z0-9_.:-]{8,160}$/.test(entryId || '')) throw new TypeError('valid entryId required');
    return this.repository.append({
      userId: context.userId,
      kind,
      entryId,
      idempotencyKey: `${context.userId}:${kind}:${entryId}`,
      payload: Object.freeze({ ...(payload || {}) }),
    });
  }

  async list(context, { kind, limit = 50 } = {}) {
    assertContext(context);
    if (!KINDS.includes(kind)) throw new TypeError('unsupported companion kind');
    if (!Number.isInteger(limit) || limit < 1 || limit > 200) throw new TypeError('invalid limit');
    return this.repository.list({ userId: context.userId, kind, limit });
  }

  async invokeOwnerTool(context, { tool, input = {} } = {}) {
    assertContext(context).requireOwner();
    const handler = this.ownerToolHandlers[tool];
    if (typeof handler !== 'function') {
      throw Object.assign(new Error('OWNER_TOOL_NOT_ALLOWED'), { code: 'OWNER_TOOL_NOT_ALLOWED' });
    }
    return handler({ userId: context.userId, input });
  }
}

module.exports = { KINDS, UserCompanionService, assertContext };
