/* global SA */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  let jobs = [];
  let filter = "active";
  let timer = null;

  function taskProgress(job) {
    const state = SA.normalizeJobState(job);
    if (state === "success") return 100;
    if (state === "running") return 58;
    if (state === "needs_user_action" || state === "failed") return 100;
    return 12;
  }

  function taskMessage(job) {
    const state = SA.normalizeJobState(job);
    if (job.receipt_message) return job.receipt_message;
    if (job.last_error_message) return job.last_error_message;
    if (state === "queued") return "已加入队列，系统会自动处理。";
    if (state === "running") return "正在处理，请保持服务在线。";
    if (state === "success") return "已完成并记录可核验回执。";
    if (state === "needs_user_action") return "自动重试未完成，请检查授权、配额或网络。";
    return "任务状态已更新。";
  }

  function visibleJobs() {
    if (filter === "all") return jobs;
    if (filter === "needs_user_action") return jobs.filter(job => ["needs_user_action", "failed"].includes(SA.normalizeJobState(job)));
    return jobs.filter(job => ["queued", "running"].includes(SA.normalizeJobState(job)));
  }

  function render() {
    const states = jobs.map(SA.normalizeJobState);
    $("runningCount").textContent = String(states.filter(state => ["queued", "running"].includes(state)).length);
    $("successCount").textContent = String(states.filter(state => state === "success").length);
    $("actionCount").textContent = String(states.filter(state => ["needs_user_action", "failed"].includes(state)).length);
    const list = visibleJobs();
    $("empty").classList.toggle("hidden", list.length !== 0);
    $("taskList").replaceChildren();
    for (const job of list) {
      const fragment = $("taskTemplate").content.cloneNode(true);
      const card = fragment.querySelector(".task-card");
      const state = SA.normalizeJobState(job);
      card.classList.add(state);
      card.querySelector(".task-title strong").textContent = SA.jobLabel(job.job_type);
      card.querySelector(".task-title small").textContent = `${job.connector_id || "系统"} · ${new Date(job.updated_at).toLocaleString("zh-CN")}`;
      card.querySelector(".task-state").textContent = SA.statusCopy(state);
      card.querySelector(".progress span").style.width = `${taskProgress(job)}%`;
      card.querySelector(".task-message").textContent = taskMessage(job);
      const retry = card.querySelector(".retry");
      retry.classList.toggle("hidden", !["needs_user_action", "failed"].includes(state));
      retry.addEventListener("click", async () => {
        retry.disabled = true;
        try {
          if (job.receipt && job.connector_id === "obsidian_local") {
            const result = await chrome.runtime.sendMessage({
              type: "SA_RETRY_LOCAL_OBSIDIAN",
              contentId: job.content_id,
              remotePath: job.remote_path
            });
            if (!result?.ok) throw new Error(result?.error || "Obsidian 本机桥接重试失败");
          } else if (job.receipt) {
            await SA.api(`/v1/destinations/receipts/${encodeURIComponent(job.receipt_id)}/retry`, { method: "POST" });
          } else {
            await SA.api(`/v1/jobs/${encodeURIComponent(job.id)}/retry`, { method: "POST" });
          }
          await refresh();
        } catch (error) {
          $("connectionBanner").textContent = `重试失败：${error?.message || "未知错误"}`;
          $("connectionBanner").classList.remove("hidden");
        } finally { retry.disabled = false; }
      });
      card.querySelector(".details").textContent = job.receipt ? "查看内容" : "查看详情";
      card.querySelector(".details").addEventListener("click", async () => {
        const config = await SA.getConfig();
        chrome.tabs.create({ url: `${config.libraryUrl}/?task=${encodeURIComponent(job.id)}` });
      });
      $("taskList").appendChild(fragment);
    }
  }

  function receiptToJob(receipt) {
    return {
      id: `receipt:${receipt.id}`,
      job_type: "export_destination",
      connector_id: receipt.destination_id,
      status: receipt.status,
      attempt_count: 1,
      created_at: receipt.attempted_at,
      updated_at: receipt.finished_at,
      receipt_id: receipt.id,
      content_id: receipt.content_id,
      remote_path: receipt.remote_path,
      evidence: receipt.evidence || {},
      last_error_code: receipt.error_code,
      last_error_message: receipt.status === "failed" ? receipt.message_zh : null,
      receipt_message: receipt.message_zh,
      receipt: true
    };
  }

  async function refresh() {
    try {
      const [jobResponse, receiptResponse] = await Promise.all([
        SA.api("/v1/jobs?limit=100", { timeoutMs: 8000 }),
        SA.api("/v1/destinations/receipts?limit=50", { timeoutMs: 8000 })
      ]);
      jobs = [...(jobResponse.items || []), ...(receiptResponse.items || []).map(receiptToJob)]
        .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
      $("connectionBanner").classList.add("hidden");
      render();
    } catch (error) {
      jobs = [];
      render();
      const banner = $("connectionBanner");
      banner.textContent = `尚未连接档案馆：${error?.message || "请先完成设置"}`;
      banner.classList.remove("hidden");
    }
  }

  $("refresh").addEventListener("click", refresh);
  $("saveCurrent").addEventListener("click", async () => {
    $("saveCurrent").disabled = true;
    try {
      const response = await chrome.runtime.sendMessage({ type: "SA_CAPTURE_ACTIVE", mode: "page", source: "task_center" });
      if (!response?.ok) throw new Error(response?.error || "保存失败");
      await refresh();
    } catch (error) {
      const banner = $("connectionBanner");
      banner.textContent = `保存失败：${error?.message || "未知错误"}`;
      banner.classList.remove("hidden");
    } finally { $("saveCurrent").disabled = false; }
  });
  $("openLibrary").addEventListener("click", async () => chrome.tabs.create({ url: (await SA.getConfig()).libraryUrl }));
  $("openSettings").addEventListener("click", () => chrome.runtime.openOptionsPage());
  for (const button of document.querySelectorAll(".segmented button")) {
    button.addEventListener("click", () => {
      filter = button.dataset.filter;
      document.querySelector(".segmented button.active")?.classList.remove("active");
      button.classList.add("active");
      render();
    });
  }

  refresh();
  timer = setInterval(refresh, 5000);
  addEventListener("unload", () => clearInterval(timer));
})();
