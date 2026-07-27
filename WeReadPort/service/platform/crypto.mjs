import {
  createCipheriv,
  createDecipheriv,
  createHash,
  createHmac,
  randomBytes,
  scrypt as scryptCallback,
  timingSafeEqual,
} from "node:crypto";
import { promisify } from "node:util";

const scrypt = promisify(scryptCallback);
const PASSWORD_N = 32_768;
const PASSWORD_R = 8;
const PASSWORD_P = 1;
const PASSWORD_LENGTH = 64;
const PASSWORD_MAXMEM = 64 * 1024 * 1024;

export function base64url(value) {
  return Buffer.from(value).toString("base64url");
}

export function fromBase64url(value) {
  return Buffer.from(String(value), "base64url");
}

export function randomToken(bytes = 32) {
  return base64url(randomBytes(bytes));
}

export function randomId(prefix = "") {
  return `${prefix}${randomToken(18)}`;
}

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function hmacHex(key, value) {
  return createHmac("sha256", key).update(value).digest("hex");
}

export function constantTimeHexEqual(left, right) {
  const a = Buffer.from(String(left), "hex");
  const b = Buffer.from(String(right), "hex");
  return a.length === b.length && timingSafeEqual(a, b);
}

export function normalizeEmail(value) {
  return String(value ?? "").trim().toLowerCase();
}

export function validateEmail(value) {
  const email = normalizeEmail(value);
  if (email.length < 3 || email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw new Error("请输入有效邮箱地址。");
  }
  return email;
}

export function validatePassword(value) {
  const password = String(value ?? "");
  if (password.length < 12 || password.length > 256) {
    throw new Error("密码需要 12 至 256 个字符。");
  }
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
    throw new Error("密码至少需要包含一个字母和一个数字。");
  }
  return password;
}

export async function hashPassword(value) {
  const password = validatePassword(value);
  const salt = randomBytes(16);
  const derived = await scrypt(password, salt, PASSWORD_LENGTH, {
    N: PASSWORD_N,
    r: PASSWORD_R,
    p: PASSWORD_P,
    maxmem: PASSWORD_MAXMEM,
  });
  return ["scrypt", PASSWORD_N, PASSWORD_R, PASSWORD_P, base64url(salt), base64url(derived)].join("$");
}

export async function verifyPassword(value, encoded) {
  const parts = String(encoded ?? "").split("$");
  if (parts.length !== 6 || parts[0] !== "scrypt") return false;
  const [, nRaw, rRaw, pRaw, saltRaw, digestRaw] = parts;
  const expected = fromBase64url(digestRaw);
  if (expected.length !== PASSWORD_LENGTH) return false;
  let derived;
  try {
    derived = await scrypt(String(value ?? ""), fromBase64url(saltRaw), PASSWORD_LENGTH, {
      N: Number(nRaw), r: Number(rRaw), p: Number(pRaw), maxmem: PASSWORD_MAXMEM,
    });
  } catch {
    return false;
  }
  return timingSafeEqual(expected, derived);
}

export function parseKeyring(raw, activeKeyId) {
  let parsed;
  try {
    parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch {
    throw new Error("WRP_KEYRING_JSON 不是有效 JSON。");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("密钥环必须是对象。");
  const keys = new Map();
  for (const [id, value] of Object.entries(parsed)) {
    const key = Buffer.from(String(value), "base64");
    if (!/^[A-Za-z0-9._-]{1,64}$/.test(id) || key.length !== 32) throw new Error("密钥环中的每个密钥必须是 32 字节 Base64。 ");
    keys.set(id, key);
  }
  if (!keys.has(activeKeyId)) throw new Error("活动密钥 ID 不存在于密钥环。");
  return Object.freeze({ activeKeyId, keys });
}

export function wrapAccountKey(keyring, accountKey, accountId) {
  return encryptEnvelope(keyring.keys.get(keyring.activeKeyId), accountKey, `account-key:${accountId}`, keyring.activeKeyId);
}

export function unwrapAccountKey(keyring, envelope, accountId) {
  const parsed = parseEnvelope(envelope);
  const key = keyring.keys.get(parsed.keyId);
  if (!key) throw new Error("密钥版本不可用。");
  return decryptEnvelope(key, parsed, `account-key:${accountId}`);
}

export function encryptForAccount(accountKey, value, aad) {
  const payload = Buffer.isBuffer(value) ? value : Buffer.from(typeof value === "string" ? value : JSON.stringify(value), "utf8");
  return encryptEnvelope(accountKey, payload, aad, "account");
}

export function decryptForAccount(accountKey, envelope, aad) {
  const parsed = parseEnvelope(envelope);
  return decryptEnvelope(accountKey, parsed, aad);
}

export function encryptWithMaster(keyring, value, aad) {
  const payload = Buffer.isBuffer(value) ? value : Buffer.from(String(value), "utf8");
  return encryptEnvelope(keyring.keys.get(keyring.activeKeyId), payload, aad, keyring.activeKeyId);
}

export function decryptWithMaster(keyring, envelope, aad) {
  const parsed = parseEnvelope(envelope);
  const key = keyring.keys.get(parsed.keyId);
  if (!key) throw new Error("密钥版本不可用。");
  return decryptEnvelope(key, parsed, aad);
}

function encryptEnvelope(key, payload, aad, keyId) {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  cipher.setAAD(Buffer.from(aad, "utf8"));
  const ciphertext = Buffer.concat([cipher.update(payload), cipher.final()]);
  const tag = cipher.getAuthTag();
  return ["v1", keyId, base64url(iv), base64url(tag), base64url(ciphertext)].join(".");
}

function parseEnvelope(value) {
  const [version, keyId, iv, tag, ciphertext, ...extra] = String(value ?? "").split(".");
  if (version !== "v1" || !keyId || !iv || !tag || !ciphertext || extra.length) throw new Error("加密信封无效。");
  return { keyId, iv: fromBase64url(iv), tag: fromBase64url(tag), ciphertext: fromBase64url(ciphertext) };
}

function decryptEnvelope(key, envelope, aad) {
  const decipher = createDecipheriv("aes-256-gcm", key, envelope.iv);
  decipher.setAAD(Buffer.from(aad, "utf8"));
  decipher.setAuthTag(envelope.tag);
  return Buffer.concat([decipher.update(envelope.ciphertext), decipher.final()]);
}

export function pkceChallenge(verifier) {
  return base64url(createHash("sha256").update(verifier).digest());
}

export function sanitizeText(value, maxLength = 240) {
  return String(value ?? "").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, maxLength);
}
