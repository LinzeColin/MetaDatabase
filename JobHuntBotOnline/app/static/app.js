document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (event) => {
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
});
