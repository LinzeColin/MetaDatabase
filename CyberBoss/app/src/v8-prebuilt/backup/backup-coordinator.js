'use strict';
const crypto = require('node:crypto');

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function assertId(value, name) {
  if (!/^[A-Za-z0-9_.-]{8,120}$/.test(value || '')) throw new TypeError(`valid ${name} required`);
}

class BackupCoordinator {
  constructor({ snapshotRuntimeDb, encryptSnapshot, decryptSnapshot, r2, oci, validateSnapshot, restoreRuntimeDb }) {
    const required = { snapshotRuntimeDb, encryptSnapshot, decryptSnapshot, validateSnapshot, restoreRuntimeDb };
    for (const [name, fn] of Object.entries(required)) if (typeof fn !== 'function') throw new TypeError(`${name} required`);
    for (const [name, client] of Object.entries({ r2, oci })) {
      if (!client || typeof client.putObject !== 'function' || typeof client.getObject !== 'function') throw new TypeError(`${name} object client required`);
    }
    Object.assign(this, { snapshotRuntimeDb, encryptSnapshot, decryptSnapshot, r2, oci, validateSnapshot, restoreRuntimeDb });
  }

  async create({ backupId, releaseId, createdAt }) {
    assertId(backupId, 'backupId');
    assertId(releaseId, 'releaseId');
    const timestamp = new Date(createdAt);
    if (Number.isNaN(timestamp.getTime())) throw new TypeError('valid createdAt required');
    const plain = Buffer.from(await this.snapshotRuntimeDb());
    await this.validateSnapshot(plain);
    const encrypted = Buffer.from(await this.encryptSnapshot(plain));
    const digest = sha256(encrypted);
    const day = timestamp.toISOString().slice(0, 10);
    const key = `CyberBoss/backups/${day}/${backupId}.enc`;
    const metadata = Object.freeze({ sha256: digest, releaseId, createdAt: timestamp.toISOString(), bytes: encrypted.length });
    const r2Receipt = await this.r2.putObject({ key, body: encrypted, metadata });
    const ociReceipt = await this.oci.putObject({ key, body: encrypted, metadata });
    return Object.freeze({
      schemaVersion: 1,
      backupId,
      releaseId,
      key,
      sha256: digest,
      bytes: encrypted.length,
      createdAt: timestamp.toISOString(),
      r2Version: r2Receipt && (r2Receipt.versionId || r2Receipt.etag || null),
      ociVersion: ociReceipt && (ociReceipt.versionId || ociReceipt.etag || null),
    });
  }

  async restore({ receipt, source = 'r2' }) {
    if (!receipt || !receipt.key || !receipt.sha256) throw new TypeError('backup receipt required');
    if (!['r2', 'oci'].includes(source)) throw new TypeError('invalid restore source');
    const encrypted = Buffer.from(await this[source].getObject({ key: receipt.key }));
    if (encrypted.length !== receipt.bytes || sha256(encrypted) !== receipt.sha256) {
      throw Object.assign(new Error('BACKUP_INTEGRITY_FAILED'), { code: 'BACKUP_INTEGRITY_FAILED' });
    }
    const plain = Buffer.from(await this.decryptSnapshot(encrypted));
    await this.validateSnapshot(plain);
    const result = await this.restoreRuntimeDb(plain);
    return Object.freeze({ ok: true, backupId: receipt.backupId, source, restoredSha256: sha256(plain), result: result || null });
  }
}

module.exports = { BackupCoordinator, sha256, assertId };
