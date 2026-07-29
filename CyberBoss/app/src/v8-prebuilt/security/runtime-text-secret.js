'use strict';
const fs = require('node:fs'); const path = require('node:path');
const SAFE_TEXT_CREDENTIALS = new Set(['deepseek-api-key']);
function validate(value, envName) {
  const text = String(value || '').trim();
  if (text.length < 8 || text.length > 4096 || /[\r\n\0]/.test(text)) throw Object.assign(new Error(`${envName}_INVALID`), { code: `${envName}_INVALID` });
  return text;
}
function loadRuntimeTextSecret({ env = process.env, envName, credentialName }) {
  if (!SAFE_TEXT_CREDENTIALS.has(credentialName)) throw new TypeError('credentialName not allowed');
  if (env[envName]) return validate(env[envName], envName);
  const dir = env.CREDENTIALS_DIRECTORY;
  if (!dir || !path.isAbsolute(dir)) throw Object.assign(new Error(`${envName}_OR_SYSTEMD_CREDENTIAL_REQUIRED`), { code: `${envName}_MISSING` });
  const resolvedDir = fs.realpathSync(dir); const resolved = fs.realpathSync(path.join(dir, credentialName));
  if (path.dirname(resolved) !== resolvedDir) throw Object.assign(new Error('CREDENTIAL_PATH_ESCAPE'), { code: 'CREDENTIAL_PATH_ESCAPE' });
  const stat = fs.statSync(resolved);
  if (!stat.isFile() || stat.size > 4096) throw Object.assign(new Error('CREDENTIAL_FILE_INVALID'), { code: 'CREDENTIAL_FILE_INVALID' });
  return validate(fs.readFileSync(resolved, 'utf8'), envName);
}
module.exports = { loadRuntimeTextSecret, SAFE_TEXT_CREDENTIALS };
