'use strict';
const crypto = require('node:crypto');

function importIdentity({ userId, source, sourceHash }) {
  if (!userId || !source || !/^[a-f0-9]{64}$/.test(sourceHash || '')) {
    throw new TypeError('invalid import identity');
  }
  return `imp_${crypto.createHash('sha256').update(`${userId}\0${source}\0${sourceHash}`).digest('base64url').slice(0, 26)}`;
}

class MemoryImportLedger {
  constructor() { this.rows = new Map(); }
  begin(input) {
    const id = importIdentity(input);
    const existing = this.rows.get(id);
    if (existing) return { ...existing, duplicate: true };
    const row = { id, ...input, state: 'preflight', checkpoint: null, importedRecords: 0 };
    this.rows.set(id, row);
    return { ...row, duplicate: false };
  }
  checkpoint(id, checkpoint, importedRecords) {
    const row = this.rows.get(id);
    if (!row) throw new Error('IMPORT_NOT_FOUND');
    row.state = 'running'; row.checkpoint = checkpoint; row.importedRecords = importedRecords;
    return { ...row };
  }
  complete(id, importedRecords) {
    const row = this.rows.get(id);
    if (!row) throw new Error('IMPORT_NOT_FOUND');
    row.state = 'completed'; row.importedRecords = importedRecords;
    return { ...row };
  }
}

module.exports = { importIdentity, MemoryImportLedger };
