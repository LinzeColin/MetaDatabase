'use strict';

class FairUserQueue {
  constructor({ perUserLimit = 1, totalLimit = 2 } = {}) {
    if (!Number.isInteger(perUserLimit) || perUserLimit < 1) throw new TypeError('invalid perUserLimit');
    if (!Number.isInteger(totalLimit) || totalLimit < 1) throw new TypeError('invalid totalLimit');
    this.perUserLimit = perUserLimit;
    this.totalLimit = totalLimit;
    this.pending = new Map();
    this.order = [];
    this.activeByUser = new Map();
    this.activeTotal = 0;
  }

  enqueue(job) {
    if (!job || !job.id || !job.userId) throw new TypeError('job id and userId required');
    if (!this.pending.has(job.userId)) {
      this.pending.set(job.userId, []);
      this.order.push(job.userId);
    }
    this.pending.get(job.userId).push({ ...job });
  }

  claimNext() {
    if (this.activeTotal >= this.totalLimit || this.order.length === 0) return null;
    for (let index = 0; index < this.order.length; index += 1) {
      const userId = this.order.shift();
      const active = this.activeByUser.get(userId) || 0;
      const jobs = this.pending.get(userId) || [];
      if (jobs.length > 0) this.order.push(userId);
      if (active >= this.perUserLimit || jobs.length === 0) continue;
      const job = jobs.shift();
      if (jobs.length === 0) {
        this.pending.delete(userId);
        this.order = this.order.filter((candidate) => candidate !== userId);
      }
      this.activeByUser.set(userId, active + 1);
      this.activeTotal += 1;
      return job;
    }
    return null;
  }

  complete(job) {
    const active = this.activeByUser.get(job.userId) || 0;
    if (active < 1) throw new Error('job was not active');
    if (active === 1) this.activeByUser.delete(job.userId);
    else this.activeByUser.set(job.userId, active - 1);
    this.activeTotal -= 1;
  }
}

module.exports = { FairUserQueue };
