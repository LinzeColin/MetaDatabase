import { collectNotebookSummaries, collectSnapshot } from "../core/collector.js";
import { createDemoCaller } from "../core/demo.js";
import { toSafeFailure, WeReadPortError } from "../core/errors.js";
import { buildExport } from "../core/exporter.js";
import { createCollectorCaller, createGatewayClient } from "../core/gateway.js";
import { importLocalFiles } from "../core/local-import.js";

let key = "";
let mode = "real";
let summaries = [];
let localSnapshot;
let localPreviousZip;
let localImportKind;
let activeController;
const realCaller = createCollectorCaller(createGatewayClient({ mode: "proxy" }));

self.onmessage = async event => {
  const message = event.data ?? {};
  try {
    if (message.type === "connect") {
      disconnect();
      mode = message.mode === "demo" ? "demo" : "real";
      key = mode === "demo" ? "demo-only" : String(message.key ?? "");
      activeController = new AbortController();
      const call = mode === "demo" ? createDemoCaller() : realCaller;
      summaries = await collectNotebookSummaries({ key, call, signal: activeController.signal, onProgress: text => postMessage({ type: "progress", text }) });
      postMessage({ type: "connected", mode, summaries });
      return;
    }

    if (message.type === "import") {
      disconnect();
      mode = "local";
      activeController = new AbortController();
      postMessage({ type: "progress", text: "正在本地校验并读取所选笔记文件…" });
      const imported = await importLocalFiles(Array.isArray(message.files) ? message.files : []);
      if (activeController.signal.aborted) throw new WeReadPortError("CANCELLED", "本地导入已取消。");
      localSnapshot = imported.snapshot;
      localPreviousZip = imported.previousZip;
      localImportKind = imported.kind;
      summaries = imported.summaries;
      key = "local-only";
      postMessage({ type: "connected", mode, summaries, importInfo: imported.info });
      return;
    }

    if (message.type === "export") {
      if (!key || !summaries.length) throw new WeReadPortError("INVALID_REQUEST", "当前来源已失效，请重新开始。");
      activeController = new AbortController();
      const selected = new Set(Array.isArray(message.selectedIds) ? message.selectedIds : []);
      const chosen = summaries.filter(item => selected.has(item.bookId));
      let snapshot;
      if (mode === "local") {
        if (!localSnapshot) throw new WeReadPortError("LOCAL_IMPORT", "本地笔记快照已清除，请重新上传。");
        snapshot = {
          ...localSnapshot,
          exportProfile: message.profile,
          books: localSnapshot.books.filter(book => selected.has(book.source.bookId)),
          failures: [],
          readingStatistics: message.includeReadingStatistics ? localSnapshot.readingStatistics : undefined,
        };
        postMessage({ type: "progress", text: `正在整理 ${snapshot.books.length} 个本地笔记文件…` });
      } else {
        const call = mode === "demo" ? createDemoCaller() : realCaller;
        snapshot = await collectSnapshot({
          key,
          summaries: chosen,
          exportProfile: message.profile,
          call,
          signal: activeController.signal,
          includeReadingStatistics: Boolean(message.includeReadingStatistics),
          onProgress: (done, total, title) => postMessage({ type: "progress", text: `正在读取 ${done}/${total}：《${title}》` }),
        });
      }
      postMessage({ type: "progress", text: "正在生成中文笔记、离线搜索、ChatGPT 阅读文件和可复核压缩包…" });
      const explicitPrevious = message.previousZip instanceof ArrayBuffer ? new Uint8Array(message.previousZip) : undefined;
      const previousZip = explicitPrevious ?? localPreviousZip;
      const result = await buildExport(snapshot, {
        profile: message.profile,
        includeCover: Boolean(message.includeCover),
        includeOfflineSearch: message.includeOfflineSearch !== false,
        previousZip,
        knownSourceBookIds: summaries.map(item => item.bookId),
        sourceInventoryComplete: true,
        retainUnselectedPrevious: !(mode === "local" && localImportKind === "archive"),
        retainPreviousTombstones: !(mode === "local" && localImportKind === "archive"),
      });
      const zipBuffer = result.bytes.buffer.slice(result.bytes.byteOffset, result.bytes.byteOffset + result.bytes.byteLength);
      let chatgpt;
      const transfer = [zipBuffer];
      if (result.chatgpt) {
        const chatgptBuffer = result.chatgpt.bytes.buffer.slice(result.chatgpt.bytes.byteOffset, result.chatgpt.bytes.byteOffset + result.chatgpt.bytes.byteLength);
        chatgpt = { filename: result.chatgpt.filename, sha256: result.chatgpt.sha256, prompt: result.chatgpt.prompt, bytes: chatgptBuffer };
        transfer.push(chatgptBuffer);
      }
      postMessage({
        type: "exported",
        filename: result.filename,
        status: result.status,
        manifest: result.manifest,
        bytes: zipBuffer,
        chatgpt,
      }, transfer);
      return;
    }

    if (message.type === "cancel") { activeController?.abort(new WeReadPortError("CANCELLED", "操作已取消。")); return; }
    if (message.type === "disconnect") { disconnect(); postMessage({ type: "disconnected" }); }
  } catch (error) {
    // 连接或本地导入失败后，不保留用户密钥或上传内容。
    if (["connect", "import"].includes(message.type)) disconnect();
    const safe = toSafeFailure(error);
    postMessage({ type: "error", error: safe });
  }
};

function disconnect() {
  activeController?.abort();
  activeController = undefined;
  key = "";
  summaries = [];
  mode = "real";
  localSnapshot = undefined;
  localPreviousZip = undefined;
  localImportKind = undefined;
}
