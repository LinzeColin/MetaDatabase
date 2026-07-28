import { hostname } from "node:os";
import { randomUUID } from "node:crypto";
import { loadConfig } from "./platform/config.mjs";
import { PlatformStore } from "./platform/store.mjs";
import { createObjectStore } from "./platform/object-store.mjs";
import { PlatformService } from "./platform/service.mjs";

const config = loadConfig();
const store = new PlatformStore(config.databasePath);
const service = new PlatformService({ store, objectStore: createObjectStore(config), config });
const workerId = `import-${hostname()}-${process.pid}-${randomUUID().slice(0, 8)}`;
let stopping = false;

const heartbeat = () => {
  try { store.heartbeat(workerId, "import", "v0.0.0.1.9"); }
  catch (error) { console.error(JSON.stringify({ event: "worker_heartbeat_failed", code: String(error?.code || "HEARTBEAT_FAILED") })); }
};
heartbeat();
const heartbeatTimer = setInterval(heartbeat, Math.max(5_000, Math.floor(config.workerStaleSeconds * 1000 / 3)));

try {
  while (!stopping) {
    try {
      const job = await service.processNextImportJob(workerId);
      if (!job) await sleep(1_500);
    } catch (error) {
      console.error(JSON.stringify({ event: "import_job_failed", code: String(error?.code || "IMPORT_FAILED") }));
      await sleep(3_000);
    }
  }
} finally {
  clearInterval(heartbeatTimer);
  store.close();
}

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
process.on("SIGTERM", () => { stopping = true; });
process.on("SIGINT", () => { stopping = true; });
