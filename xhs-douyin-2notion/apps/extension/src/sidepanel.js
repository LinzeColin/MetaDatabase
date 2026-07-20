import { recognizePage } from "./page-support.js";

const tabs = [...document.querySelectorAll('[role="tab"]')];
const panels = [...document.querySelectorAll('[role="tabpanel"]')];
const pageStatus = document.querySelector("#page-status");
const platformStatus = document.querySelector("#platform-status");
const hostStatus = document.querySelector("#host-status");
const refreshButton = document.querySelector("#refresh-status");

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
    return recognizePage(tab?.url ?? "");
  } catch {
    return recognizePage("");
  }
}

function renderPage(result) {
  if (result.supported) {
    pageStatus.textContent = "Supported page recognized";
    platformStatus.textContent = `${result.platform}: disabled until its platform gate passes`;
    return;
  }
  pageStatus.textContent = "No executable save for this page";
  platformStatus.textContent = result.reason;
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
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refreshStatus().catch(() => undefined);
});

selectTab(tabs[0]);
activePage().then(renderPage).catch(() => renderPage(recognizePage("")));
refreshStatus().catch(() => undefined);
