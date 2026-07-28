"use strict";

// CB-630 / AC-008, AC-044: one active turn per user, round-robin between users
// and a bounded global concurrency. The Owner's Codex lane is counted and
// limited separately so a busy Owner cannot starve ordinary users and a burst
// of ordinary users cannot block the Owner.

const DEFAULTS = Object.freeze({
  perUserActive: 1,
  perUserQueued: 3,
  globalActive: 2,
  ownerActive: 1,
});

class FairQueueError extends Error {
  constructor(code) {
    super(code);
    this.name = "FairQueueError";
    this.code = code;
  }
}

function positiveInteger(value, field) {
  if (!Number.isSafeInteger(value) || value < 1 || value > 1000) {
    throw new FairQueueError(`${field.toUpperCase()}_INVALID`);
  }
  return value;
}

class FairUserQueue {
  constructor({
    perUserActive = DEFAULTS.perUserActive,
    perUserQueued = DEFAULTS.perUserQueued,
    globalActive = DEFAULTS.globalActive,
    ownerActive = DEFAULTS.ownerActive,
  } = {}) {
    this.perUserActive = positiveInteger(perUserActive, "per_user_active");
    this.perUserQueued = positiveInteger(perUserQueued, "per_user_queued");
    this.globalActive = positiveInteger(globalActive, "global_active");
    this.ownerActive = positiveInteger(ownerActive, "owner_active");
    this.pending = new Map();
    this.rotation = [];
    this.activeByUser = new Map();
    this.activeJobs = new Map();
    this.activeTotal = 0;
    this.activeOwner = 0;
    this.seenJobIds = new Set();
  }

  // AC-009 at the queue layer: the same job id can only ever be admitted once,
  // so a duplicated provider message cannot produce a second turn.
  enqueue({ jobId, userId, isOwner = false }) {
    if (typeof jobId !== "string" || jobId.length === 0) {
      throw new FairQueueError("JOB_ID_REQUIRED");
    }
    if (typeof userId !== "string" || userId.length === 0) {
      throw new FairQueueError("USER_ID_REQUIRED");
    }
    if (this.seenJobIds.has(jobId)) {
      return Object.freeze({ admitted: false, reason: "duplicate_job" });
    }
    const queued = this.pending.get(userId) || [];
    if (queued.length >= this.perUserQueued) {
      return Object.freeze({ admitted: false, reason: "user_queue_full" });
    }
    if (queued.length === 0) {
      this.pending.set(userId, queued);
      this.rotation.push(userId);
    }
    queued.push(Object.freeze({ jobId, userId, isOwner: Boolean(isOwner) }));
    this.seenJobIds.add(jobId);
    return Object.freeze({
      admitted: true,
      reason: "queued",
      queuedForUser: queued.length,
    });
  }

  // Round-robin: the head user is rotated to the back whether or not it was
  // eligible, so no user can hold the front of the queue.
  claimNext() {
    if (this.activeTotal >= this.globalActive || this.rotation.length === 0) {
      return null;
    }
    for (let attempt = 0; attempt < this.rotation.length; attempt += 1) {
      const userId = this.rotation.shift();
      const queued = this.pending.get(userId) || [];
      if (queued.length === 0) {
        this.pending.delete(userId);
        continue;
      }
      this.rotation.push(userId);
      if ((this.activeByUser.get(userId) || 0) >= this.perUserActive) {
        continue;
      }
      const next = queued[0];
      if (next.isOwner && this.activeOwner >= this.ownerActive) {
        continue;
      }
      queued.shift();
      if (queued.length === 0) {
        this.pending.delete(userId);
        this.rotation = this.rotation.filter((candidate) => candidate !== userId);
      }
      this.activeByUser.set(userId, (this.activeByUser.get(userId) || 0) + 1);
      this.activeJobs.set(next.jobId, next);
      this.activeTotal += 1;
      if (next.isOwner) {
        this.activeOwner += 1;
      }
      return next;
    }
    return null;
  }

  complete(jobId) {
    const job = this.activeJobs.get(jobId);
    if (!job) {
      throw new FairQueueError("JOB_NOT_ACTIVE");
    }
    this.activeJobs.delete(jobId);
    const active = this.activeByUser.get(job.userId) || 0;
    if (active <= 1) {
      this.activeByUser.delete(job.userId);
    } else {
      this.activeByUser.set(job.userId, active - 1);
    }
    this.activeTotal -= 1;
    if (job.isOwner) {
      this.activeOwner -= 1;
    }
    return job;
  }

  activeForUser(userId) {
    return this.activeByUser.get(userId) || 0;
  }

  queuedForUser(userId) {
    return (this.pending.get(userId) || []).length;
  }

  // Field names and values here are counts only: safe for Status (AC-032).
  metrics() {
    return Object.freeze({
      active_total: this.activeTotal,
      active_owner: this.activeOwner,
      queued_total: [...this.pending.values()].reduce(
        (total, queue) => total + queue.length,
        0,
      ),
      waiting_users: this.pending.size,
      per_user_active_limit: this.perUserActive,
      per_user_queued_limit: this.perUserQueued,
      global_active_limit: this.globalActive,
    });
  }
}

module.exports = { DEFAULTS, FairQueueError, FairUserQueue };
