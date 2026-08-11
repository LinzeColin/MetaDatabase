document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.matches("[data-live-filters]")) return;
      const confirmMessage = form.dataset.confirm;
      if (confirmMessage && !window.confirm(confirmMessage)) {
        event.preventDefault();
        return;
      }
      const button = form.querySelector('button[type="submit"]');
      if (button) {
        button.setAttribute("aria-busy", "true");
        button.disabled = true;
        button.dataset.originalText = button.textContent;
        button.textContent = "处理中…";
      }
    });
  });

  const fileInput = document.querySelector("#resume-file");
  const selectedFile = document.querySelector("#selected-file");
  if (fileInput && selectedFile) {
    fileInput.addEventListener("change", () => {
      selectedFile.textContent = fileInput.files?.[0]?.name || "尚未选择文件";
    });
  }

  document.querySelectorAll(".copy-button").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy || "");
        button.textContent = "已复制";
      } catch {
        button.textContent = "复制失败";
      }
      setTimeout(() => { button.textContent = "复制"; }, 1200);
    });
  });

  const filterForm = document.querySelector("[data-live-filters]");
  const results = document.querySelector("#recommendation-results");
  const liveStatus = document.querySelector("#filter-live-status");
  if (filterForm && results) {
    let debounceTimer;
    let currentRequest;
    const updateResults = async () => {
      if (currentRequest) currentRequest.abort();
      const request = new AbortController();
      currentRequest = request;
      const visibleParams = new URLSearchParams(new FormData(filterForm));
      const requestParams = new URLSearchParams(visibleParams);
      requestParams.set("partial", "true");
      results.setAttribute("aria-busy", "true");
      if (liveStatus) liveStatus.textContent = "正在更新结果…";
      try {
        const response = await fetch(`${filterForm.action}?${requestParams.toString()}`, {
          headers: { "X-Requested-With": "JobHuntBot" },
          credentials: "same-origin",
          signal: request.signal,
        });
        if (!response.ok) throw new Error(`filter request failed: ${response.status}`);
        if (currentRequest !== request) return;
        results.innerHTML = await response.text();
        const count = results.querySelector("[data-result-count]")?.dataset.resultCount;
        if (liveStatus) liveStatus.textContent = `结果已更新${count === undefined ? "" : `，共 ${count} 个`}`;
        const query = visibleParams.toString();
        window.history.replaceState({}, "", `${filterForm.action}${query ? `?${query}` : ""}`);
      } catch (error) {
        if (currentRequest === request && error.name !== "AbortError" && liveStatus) liveStatus.textContent = "筛选更新失败，请重试。";
      } finally {
        if (currentRequest === request) results.removeAttribute("aria-busy");
      }
    };
    const scheduleUpdate = () => {
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(updateResults, 250);
    };
    filterForm.addEventListener("submit", (event) => {
      event.preventDefault();
      window.clearTimeout(debounceTimer);
      updateResults();
    });
    filterForm.querySelectorAll("select").forEach((input) => input.addEventListener("change", scheduleUpdate));
    filterForm.querySelectorAll("input[type='text'], input[type='search']").forEach((input) => input.addEventListener("input", scheduleUpdate));
  }
});
