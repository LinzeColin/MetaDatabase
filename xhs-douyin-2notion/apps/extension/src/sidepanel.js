import { recognizePage } from "./page-support.js";

const tabs = [...document.querySelectorAll('[role="tab"]')];
const panels = [...document.querySelectorAll('[role="tabpanel"]')];
const pageStatus = document.querySelector("#page-status");
const platformStatus = document.querySelector("#platform-status");
const hostStatus = document.querySelector("#host-status");
const refreshButton = document.querySelector("#refresh-status");
const saveButton = document.querySelector("#save-current");
const captureStatus = document.querySelector("#capture-status");
let activeTabId = null;
let currentPageExecutable = false;
let captureInFlight = false;
let pageRefreshGeneration = 0;
const EXECUTABLE_PLATFORM_NAMES = Object.freeze({
  bilibili: "Bilibili",
  douyin: "Douyin",
  kuaishou: "Kuaishou",
  taobao: "Taobao",
  weibo: "Weibo",
  xiaohongshu: "Xiaohongshu",
});

function selectTab(selected) {
  for (const tab of tabs) {
    const active = tab === selected;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  }
  for (const panel of panels) panel.hidden = panel.id !== selected.getAttribute("aria-controls");
}

for (const tab of tabs) {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (!new Set(["ArrowLeft", "ArrowRight"]).has(event.key)) return;
    event.preventDefault();
    const offset = event.key === "ArrowRight" ? 1 : -1;
    const next = tabs[(tabs.indexOf(tab) + offset + tabs.length) % tabs.length];
    selectTab(next);
    next.focus();
  });
}

async function activePage() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    return { ...recognizePage(tab?.url ?? ""), tabId: tab?.id ?? null };
  } catch {
    return { ...recognizePage(""), tabId: null };
  }
}

function renderPage(result) {
  activeTabId = Number.isSafeInteger(result.tabId) ? result.tabId : null;
  const executablePlatform = result.executable
    && Object.hasOwn(EXECUTABLE_PLATFORM_NAMES, result.platform)
    && activeTabId !== null;
  currentPageExecutable = executablePlatform;
  saveButton.disabled = !executablePlatform;
  saveButton.textContent = saveButton.disabled ? "Save unavailable" : "Save current page";
  if (!captureInFlight) {
    captureStatus.textContent = "";
    delete captureStatus.dataset.jobId;
  }
  if (executablePlatform) {
    const platformName = EXECUTABLE_PLATFORM_NAMES[result.platform];
    pageStatus.textContent = `${platformName} detail page recognized`;
    platformStatus.textContent = "Only this explicitly selected current page will be read";
    return;
  }
  if (result.supported) {
    pageStatus.textContent = "Supported page recognized";
    platformStatus.textContent = `${result.platform}: current-page gate remains disabled`;
    return;
  }
  pageStatus.textContent = "No executable save for this page";
  platformStatus.textContent = result.reason;
}

async function refreshPage() {
  const generation = ++pageRefreshGeneration;
  const result = await activePage();
  if (generation === pageRefreshGeneration) renderPage(result);
}

async function captureCurrentPage() {
  if (activeTabId === null || saveButton.disabled || captureInFlight) return;
  const requestedTabId = activeTabId;
  captureInFlight = true;
  saveButton.disabled = true;
  captureStatus.textContent = "Reading sanitized current-page facts…";
  const pendingNotice = setTimeout(() => {
    captureStatus.textContent = "Still waiting for local confirmation — do not retry";
  }, 15_000);
  try {
    const result = await chrome.runtime.sendMessage({ tabId: requestedTabId, type: "X2N_CAPTURE_CURRENT" });
    if (result?.ok && result.response?.job_id) {
      captureStatus.dataset.jobId = result.response.job_id;
      captureStatus.textContent = result.response.status === "completed"
        ? "Current page committed to the canonical store"
        : "Current page queued in the local companion";
    } else if (result?.code === "X2N_PLATFORM_CHANGED") {
      captureStatus.textContent = "Page structure changed — capture stopped without saving";
    } else if (result?.status === "active_tab_permission_required") {
      captureStatus.textContent = "Reopen x2n from the toolbar on this page, then try again";
    } else {
      captureStatus.textContent = "Capture unavailable — no action executed";
    }
  } catch {
    captureStatus.textContent = "Capture unavailable — no action executed";
  } finally {
    clearTimeout(pendingNotice);
    captureInFlight = false;
    saveButton.disabled = !(currentPageExecutable && activeTabId === requestedTabId);
  }
}

async function refreshStatus() {
  refreshButton.disabled = true;
  hostStatus.textContent = "Checking local companion…";
  try {
    const result = await Promise.race([
      chrome.runtime.sendMessage({ type: "X2N_HEALTH" }),
      new Promise((resolve) => setTimeout(() => resolve({ ok: false }), 4_000)),
    ]);
    hostStatus.textContent = result?.ok ? "Local companion connected" : "Local companion unavailable — no action executed";
  } catch {
    hostStatus.textContent = "Local companion unavailable — no action executed";
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", refreshStatus);
saveButton.addEventListener("click", captureCurrentPage);
chrome.tabs.onActivated.addListener(() => {
  refreshPage().catch(() => undefined);
});
chrome.tabs.onUpdated.addListener((_tabId, changeInfo) => {
  if (changeInfo.status === "complete" || typeof changeInfo.url === "string") {
    refreshPage().catch(() => undefined);
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    refreshPage().catch(() => undefined);
    refreshStatus().catch(() => undefined);
  }
});

selectTab(tabs[0]);
refreshPage().catch(() => undefined);
refreshStatus().catch(() => undefined);
