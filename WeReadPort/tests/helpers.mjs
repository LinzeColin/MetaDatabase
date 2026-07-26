import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

export function userKey() {
  return `wrk-${"x".repeat(32)}`;
}

export async function fixture(name) {
  return JSON.parse(await readFile(path.join(here, "fixtures", name), "utf8"));
}

export function bytesEqual(left, right) {
  if (left.byteLength !== right.byteLength) return false;
  for (let index = 0; index < left.byteLength; index += 1) if (left[index] !== right[index]) return false;
  return true;
}
