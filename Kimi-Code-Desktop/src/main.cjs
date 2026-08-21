const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { app, BrowserWindow, Menu, dialog, shell } = require("electron");
const { HarnessBridge } = require("./runtime/harness.cjs");
const { kimiHome, resolveKimiCli } = require("./runtime/paths.cjs");
const { startKimiServer, stopKimiServer } = require("./runtime/server.cjs");

const developmentRoot = path.resolve(__dirname, "..");
const harnessCss = fs.readFileSync(path.join(__dirname, "harness.css"), "utf8");
const harnessBridge = new HarnessBridge();

let mainWindow = null;
let runtime = null;
let runtimePromise = null;
let quitting = false;
let cleanupStarted = false;

app.setName("Kimi Code Desktop");
const singleInstance = app.requestSingleInstanceLock();
if (!singleInstance) app.quit();

function buildMenu() {
  const template = [
    ...(process.platform === "darwin" ? [{ role: "appMenu" }] : []),
    {
      label: "文件",
      submenu: [
        { label: "关闭窗口", accelerator: "CmdOrCtrl+W", role: "close" },
        { type: "separator" },
        { label: "打开 Kimi 数据目录", click: () => shell.openPath(kimiHome()) },
        { type: "separator" },
        { label: "退出", accelerator: "CmdOrCtrl+Q", role: "quit" },
      ],
    },
    { role: "editMenu" },
    {
      label: "视图",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { label: "打开 Harness UI", click: () => shell.openExternal("http://127.0.0.1:3099/") },
        { role: "togglefullscreen" },
      ],
    },
    { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function ensureRuntime() {
  if (runtime?.child?.exitCode === null) return runtime;
  if (runtimePromise) return runtimePromise;
  runtimePromise = (async () => {
    const resolved = resolveKimiCli({
      homeDir: os.homedir(),
      resourcesPath: app.isPackaged ? process.resourcesPath : null,
      developmentRoot,
    });
    if (!resolved.path) {
      throw new Error(`找不到 Kimi Code CLI。已检查：\n${resolved.candidates.join("\n")}`);
    }
    runtime = await startKimiServer({
      cliPath: resolved.path,
      homeDir: kimiHome(),
      preferredPort: Number(process.env.KIMI_PORT || 58627),
    });
    return runtime;
  })();
  try { return await runtimePromise; }
  finally { runtimePromise = null; }
}

function protectNavigation(window, origin) {
  window.webContents.setWindowOpenHandler(({ url }) => {
    try {
      if (new URL(url).origin === origin) return {
        action: "allow",
        overrideBrowserWindowOptions: { webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true } },
      };
    } catch { }
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event, url) => {
    try { if (new URL(url).origin === origin) return; }
    catch { }
    event.preventDefault();
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
  });
}

async function createWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
    mainWindow.focus();
    return mainWindow;
  }
  const activeRuntime = await ensureRuntime();
  const origin = `http://127.0.0.1:${activeRuntime.port}`;
  const window = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 920,
    minHeight: 640,
    title: "Kimi Code Desktop",
    backgroundColor: "#0d1428",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow = window;
  protectNavigation(window, origin);
  window.webContents.on("did-finish-load", async () => {
    try {
      if (window.__harnessCssKey) await window.webContents.removeInsertedCSS(window.__harnessCssKey);
      window.__harnessCssKey = await window.webContents.insertCSS(harnessCss);
    }
    catch (error) { console.warn(`[kimi-desktop] Harness CSS: ${error.message}`); }
  });
  window.on("closed", () => {
    if (mainWindow === window) mainWindow = null;
    window.__harnessCssKey = null;
    harnessBridge.stop();
  });
  await window.loadURL(`${origin}/#token=${encodeURIComponent(activeRuntime.token)}`);
  harnessBridge.attach(window);
  return window;
}

async function startApplication() {
  if (!singleInstance) return;
  buildMenu();
  await createWindow();
}

app.whenReady().then(startApplication).catch(async (error) => {
  console.error(error);
  await dialog.showMessageBox({
    type: "error",
    title: "Kimi Code Desktop 启动失败",
    message: "无法启动 Kimi Code Desktop",
    detail: error.message,
  });
  app.quit();
});

app.on("second-instance", () => {
  createWindow().catch((error) => console.error(error));
});

app.on("activate", () => {
  createWindow().catch((error) => console.error(error));
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", (event) => {
  quitting = true;
  if (cleanupStarted) return;
  event.preventDefault();
  cleanupStarted = true;
  harnessBridge.stop();
  stopKimiServer(runtime)
    .catch((error) => console.error(`[kimi-desktop] 关闭 Kimi 服务失败: ${error.message}`))
    .finally(() => app.exit(0));
});

app.on("will-quit", () => {
  if (!quitting) harnessBridge.stop();
});
