import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { buildCatalog } from "../src/catalog.mjs";

function argument(name) {
  const index = process.argv.indexOf(`--${name}`);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Missing --${name}`);
  return process.argv[index + 1];
}

const sourceRoot = path.resolve(argument("source"));
const output = path.resolve(argument("output"));
const labelsFile = process.argv.includes("--labels") ? path.resolve(argument("labels")) : null;
const labels = labelsFile ? JSON.parse(fs.readFileSync(labelsFile, "utf8")) : {};
const catalog = buildCatalog({ sourceRoot, labels });
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, JSON.stringify(catalog, null, 2) + "\n");
console.log(`catalog_entries=${catalog.count}`);
console.log(`catalog_output=${output}`);
