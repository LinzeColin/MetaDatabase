const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { app, BrowserWindow, Menu, dialog, shell } = require("electron");
const { HarnessBridge } = require("./runtime/harness.cjs");
const {
  desktopUserDataPath,
  kimiHome,
  prepareStableMacCli,
  resolveKimiCli,
} = require("./runtime/paths.cjs");
const { runtimeAlive, startKimiServer, stopKimiServer } = require("./runtime/server.cjs");
const { DesktopUpdater } = require("./runtime/updater.cjs");

const developmentRoot = path.resolve(__dirname, "..");
const harnessCss = fs.readFileSync(path.join(__dirname, "harness.css"), "utf8");
const bundleId = "com.electron.kimi-code";

let mainWindow = null;
let runtime = null;
let runtimePromise = null;
let quitting = false;
let cleanupStarted = false;
let menuRebuildTimer = null;
let updateBusy = false;
let availableUpdate = null;
let updateStartupTimer = null;
let updateIntervalTimer = null;

const harnessBridge = new HarnessBridge({ onChange: () => queueMenuRebuild() });
let updater = null;

app.setName("Kimi Code");
const userDataPath = desktopUserDataPath(app.getPath("appData"));
fs.mkdirSync(userDataPath, { recursive: true });
app.setPath("userData", userDataPath);
const singleInstance = app.requestSingleInstanceLock();
if (!singleInstance) app.quit();

function displayName(value, fallback = "未命名") {
  const cleaned = String(value || fallback).replace(/[\r\n\t]/g, " ").trim();
  return cleaned.slice(0, 100) || fallback;
}

function showMessage(options) {
  return mainWindow && !mainWindow.isDestroyed()
    ? dialog.showMessageBox(mainWindow, options)
    : dialog.showMessageBox(options);
}

async function showPendingUpdateResult() {
  const updatesRoot = path.join(kimiHome(), "desktop-updates");
  const pending = path.join(updatesRoot, "pending-update-result.json");
  const archived = path.join(updatesRoot, "last-update.json");
  let receipt;
  try {
    receipt = JSON.parse(fs.readFileSync(pending, "utf8"));
    fs.renameSync(pending, archived);
  } catch (error) {
    if (error.code !== "ENOENT") console.warn(`[kimi-desktop] 更新回执读取失败: ${error.message}`);
    return;
  }
  const succeeded = receipt.status === "installed";
  await showMessage({
    type: succeeded ? "info" : "warning",
    title: "Kimi Code Desktop 更新",
    message: succeeded
      ? `已更新到 v${displayName(receipt.desktopVersion, app.getVersion())}`
      : "更新未完成，旧版已恢复运行",
    detail: displayName(receipt.detail, succeeded ? "应用本体已更新，个人数据保持原位。" : "个人数据未被修改。"),
  });
}

function queueMenuRebuild() {
  if (!app.isReady() || quitting || menuRebuildTimer) return;
  menuRebuildTimer = setTimeout(() => {
    menuRebuildTimer = null;
    buildMenu();
  }, 50);
}

function runHarnessAction(action) {
  Promise.resolve(action()).catch((error) => showMessage({
    type: "warning",
    title: "Harness UI 同步失败",
    message: "无法同步皮肤状态",
    detail: error.message,
  }));
}

function openHarnessLibrary() {
  const target = process.platform === "darwin" ? "harnessui://library" : "http://127.0.0.1:3099/";
  return shell.openExternal(target).catch((error) => showMessage({
    type: "warning",
    title: "无法打开 Harness UI",
    message: "请确认 Harness UI 已安装并正在运行",
    detail: error.message,
  }));
}

function skinMenu() {
  const { catalog, state, online, error } = harnessBridge.snapshot();
  const entries = Array.isArray(catalog.entries) ? catalog.entries : [];
  const selected = entries.find((entry) => entry.id === state.selected);
  const items = [
    { label: online ? `素材库：${entries.length} 个变体` : "Harness UI：未连接", enabled: false },
    { label: `当前：${displayName(selected?.fullLabel, "未选择")}`, enabled: false },
  ];
  if (!online && error) items.push({ label: displayName(error), enabled: false });
  items.push(
    { type: "separator" },
    { label: "打开完整素材库", click: openHarnessLibrary },
    { label: "立即同步 SMB 素材目录", click: () => runHarnessAction(async () => {
      const status = await harnessBridge.refreshCatalog();
      await showMessage({
        type: status.status === "partial" ? "warning" : "info",
        title: status.status === "partial" ? "SMB 素材未完整" : "Harness UI 素材已同步",
        message: displayName(status.message, "素材目录已刷新"),
        detail: status.status === "partial" ? "本地完整库已保留；缺少的 SMB 素材不会覆盖或删除本地内容。" : "Kimi Code、DSH 与 Harness UI 已读取同一份更新结果。",
      });
    }) },
    { label: state.mode === "rotate" ? "停止轮播" : "开启轮播", enabled: online, click: () => runHarnessAction(() => harnessBridge.patch({ mode: state.mode === "rotate" ? "gallery" : "rotate" })) },
    { label: "换下一张", accelerator: "CmdOrCtrl+Shift+N", enabled: online && entries.length > 0, click: () => runHarnessAction(() => harnessBridge.next()) },
    { type: "separator" },
  );

  const games = new Map();
  for (const entry of entries) {
    if (!games.has(entry.game)) games.set(entry.game, { label: entry.gameName, characters: new Map() });
    const game = games.get(entry.game);
    if (!game.characters.has(entry.character)) game.characters.set(entry.character, []);
    game.characters.get(entry.character).push(entry);
  }
  for (const game of games.values()) {
    const characters = [...game.characters.values()].map((variants) => {
      variants.sort((left, right) => displayName(left.variantZh).localeCompare(displayName(right.variantZh), "zh"));
      if (variants.length === 1) {
        const entry = variants[0];
        return {
          label: displayName(entry.fullLabel),
          type: "checkbox",
          checked: entry.id === state.selected,
          click: () => runHarnessAction(() => harnessBridge.patch({ mode: "gallery", selected: entry.id })),
        };
      }
      return {
        label: displayName(variants[0].characterZh),
        submenu: variants.map((entry) => ({
          label: displayName(entry.variantZh),
          type: "checkbox",
          checked: entry.id === state.selected,
          click: () => runHarnessAction(() => harnessBridge.patch({ mode: "gallery", selected: entry.id })),
        })),
      };
    });
    characters.sort((left, right) => left.label.localeCompare(right.label, "zh"));
    items.push({ label: displayName(game.label), submenu: characters });
  }
  if (!entries.length) items.push({ label: "暂无可用素材", enabled: false });
  return items;
}

async function checkForUpdates() {
  if (updateBusy || !updater) return;
  updateBusy = true;
  queueMenuRebuild();
  try {
    const result = await updater.check();
    availableUpdate = result.status === "available" ? result : null;
    if (!availableUpdate) {
      await showMessage({
        type: "info",
        title: "Kimi Code Desktop 更新",
        message: `当前没有可用更新（v${app.getVersion()}）`,
        detail: "应用只跟随 Kimi Code 官方版本号；更新仅替换应用本体，配置、会话、皮肤、素材与外置图标保持原位。",
      });
      return;
    }
    const choice = await showMessage({
      type: "info",
      title: "Kimi Code Desktop 更新",
      message: `发现新版本 v${availableUpdate.version}`,
      detail: "下载后可退出并安装。更新只替换应用本体，外部配置、会话、皮肤和素材保持不变。",
      buttons: ["下载更新", "查看发布说明", "稍后"],
      defaultId: 0,
      cancelId: 2,
    });
    if (choice.response === 1) {
      await shell.openExternal(availableUpdate.release.html_url);
      return;
    }
    if (choice.response !== 0) return;
    const archive = await updater.download(availableUpdate);
    if (process.platform !== "darwin") {
      await shell.openPath(archive);
      return;
    }
    const install = await showMessage({
      type: "question",
      title: "更新已下载",
      message: `现在退出并安装 v${availableUpdate.version}？`,
      detail: "Kimi 后台会先正常结束并释放文件权限；安装完成后应用会自动重新打开。",
      buttons: ["退出并安装", "稍后"],
      defaultId: 0,
      cancelId: 1,
    });
    if (install.response === 0) {
      updater.prepareMacInstall({ archive, version: availableUpdate.version });
      app.quit();
    }
  } catch (error) {
    await showMessage({
      type: "warning",
      title: "无法完成更新检查",
      message: "Kimi Code Desktop 更新未执行",
      detail: error.message,
    });
  } finally {
    updateBusy = false;
    queueMenuRebuild();
  }
}

async function checkForUpdatesInBackground() {
  if (updateBusy || !updater) return;
  try {
    const result = await updater.check();
    availableUpdate = result.status === "available" ? result : null;
    queueMenuRebuild();
  } catch { }
}

async function openFullDiskAccessSettings() {
  try {
    await shell.openExternal("x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles");
  } catch (error) {
    await showMessage({
      type: "warning",
      title: "无法打开系统设置",
      message: "请手动打开“隐私与安全性 → 完整磁盘访问权限”",
      detail: error.message,
    });
  }
}

function buildMenu() {
  const updateLabel = updateBusy
    ? "正在检查更新…"
    : availableUpdate ? `下载更新 v${availableUpdate.version}…` : "检查更新…";
  const macAppMenu = {
    label: app.name,
    submenu: [
      { role: "about" },
      { label: updateLabel, enabled: !updateBusy, click: checkForUpdates },
      { label: "打开完整磁盘访问设置…", click: openFullDiskAccessSettings },
      { type: "separator" },
      { role: "services" },
      { type: "separator" },
      { role: "hide" },
      { role: "hideOthers" },
      { role: "unhide" },
      { type: "separator" },
      { role: "quit" },
    ],
  };
  const template = [
    ...(process.platform === "darwin" ? [macAppMenu] : []),
    {
      label: "文件",
      submenu: [
        { label: "关闭窗口", accelerator: "CmdOrCtrl+W", role: "close" },
        { type: "separator" },
        { label: "打开 Kimi 数据目录", click: () => shell.openPath(kimiHome()) },
        ...(process.platform === "darwin" ? [{ label: "打开完整磁盘访问设置…", click: openFullDiskAccessSettings }] : []),
        { type: "separator" },
        { label: "退出", accelerator: "CmdOrCtrl+Q", role: "quit" },
      ],
    },
    { label: "皮肤", submenu: skinMenu() },
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
        { role: "togglefullscreen" },
      ],
    },
    { role: "windowMenu" },
    ...(process.platform === "darwin" ? [] : [{ label: "帮助", submenu: [{ label: updateLabel, enabled: !updateBusy, click: checkForUpdates }] }]),
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function ensureRuntime() {
  if (runtimeAlive(runtime)) return runtime;
  if (runtimePromise) return runtimePromise;
  runtimePromise = (async () => {
    const stableCli = app.isPackaged && process.platform === "darwin" && !process.env.KIMI_CLI_PATH
      ? prepareStableMacCli({
        expectedVersion: app.getVersion(),
        kimiHomeDir: kimiHome(),
        resourcesPath: process.resourcesPath,
      })
      : null;
    const resolved = resolveKimiCli({
      env: stableCli ? { ...process.env, KIMI_CLI_PATH: stableCli } : process.env,
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
      launchdLabel: app.isPackaged && process.platform === "darwin" ? `${bundleId}.backend` : null,
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
    title: "Kimi Code",
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
    const previousCssKey = window.__harnessCssKey;
    window.__harnessCssKey = null;
    if (previousCssKey) {
      try { await window.webContents.removeInsertedCSS(previousCssKey); }
      catch (error) { console.warn(`[kimi-desktop] 旧 Harness CSS 已随页面重载释放: ${error.message}`); }
    }
    try {
      window.__harnessCssKey = await window.webContents.insertCSS(harnessCss);
      await harnessBridge.reapply(window);
    }
    catch (error) { console.warn(`[kimi-desktop] Harness CSS: ${error.message}`); }
  });
  window.on("closed", () => {
    if (mainWindow === window) mainWindow = null;
    window.__harnessCssKey = null;
    harnessBridge.detach(window);
  });
  await window.loadURL(`${origin}/#token=${encodeURIComponent(activeRuntime.token)}`);
  harnessBridge.attach(window);
  return window;
}

async function startApplication() {
  if (!singleInstance) return;
  updater = new DesktopUpdater({
    currentVersion: app.getVersion(),
    updatesRoot: path.join(kimiHome(), "desktop-updates"),
    installerSource: path.join(__dirname, "update", "install-macos.sh"),
    bundleId,
  });
  updater.rememberMacInstallLocation();
  updater.quarantineLegacyMacRollbacks();
  const personalizationRoot = path.join(kimiHome(), "personalization", "kimi-code-desktop");
  const customIcon = ["icon.png", "icon.icns"]
    .map((name) => path.join(personalizationRoot, name))
    .find((candidate) => fs.existsSync(candidate));
  if (process.platform === "darwin" && app.dock && customIcon) app.dock.setIcon(customIcon);
  harnessBridge.start();
  buildMenu();
  await createWindow();
  await showPendingUpdateResult();
  if (app.isPackaged) {
    updateStartupTimer = setTimeout(checkForUpdatesInBackground, 30000);
    updateStartupTimer.unref?.();
    updateIntervalTimer = setInterval(checkForUpdatesInBackground, 6 * 60 * 60 * 1000);
    updateIntervalTimer.unref?.();
  }
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
  if (updateStartupTimer) clearTimeout(updateStartupTimer);
  if (updateIntervalTimer) clearInterval(updateIntervalTimer);
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
