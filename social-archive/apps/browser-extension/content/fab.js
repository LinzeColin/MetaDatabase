(() => {
  "use strict";
  const ID = "social-archive-save-fab";
  if (document.getElementById(ID)) return;
  const button = document.createElement("button");
  button.id = ID;
  button.type = "button";
  // **一个动作只能有一个名字。**
  //
  // 这里原来叫「保存到我的档案馆」，而插件弹窗上那颗叫「保存当前页面」——
  // 同一件事两个名字。更糟的是服务端的文案写着「点**插件的**
  // 「保存到我的档案馆」」：那个名字确实存在，但它在网页上这颗悬浮按钮上，
  // 不在插件弹窗里。他会打开弹窗，找不到，然后卡住。
  // 这个仓自己写过一句话：**指错方向的下一步，比不给下一步更坏。**
  button.textContent = "保存当前页面";
  button.setAttribute("aria-label", "保存当前页面到 Social Archive");
  Object.assign(button.style, {
    position: "fixed", right: "20px", bottom: "24px", zIndex: "2147483647",
    border: "0", borderRadius: "999px", padding: "12px 16px", cursor: "pointer",
    font: "600 14px/1.2 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    color: "#fff", background: "#171717", boxShadow: "0 8px 30px rgba(0,0,0,.25)",
    transition: "transform .16s ease,opacity .16s ease"
  });
  button.addEventListener("mouseenter", () => { button.style.transform = "translateY(-2px)"; });
  button.addEventListener("mouseleave", () => { button.style.transform = "translateY(0)"; });
  button.addEventListener("click", async () => {
    if (button.dataset.busy === "1") return;
    button.dataset.busy = "1";
    const original = button.textContent;
    button.textContent = "正在保存…";
    try {
      const response = await chrome.runtime.sendMessage({ type: "SA_CAPTURE_ACTIVE", mode: "page", source: "floating_button" });
      if (!response?.ok) throw new Error(response?.error || "保存失败");
      button.textContent = "已保存";
    } catch (error) {
      button.textContent = "需要处理";
      button.title = error?.message || "保存失败";
    } finally {
      setTimeout(() => {
        button.dataset.busy = "0";
        button.textContent = original;
      }, 1800);
    }
  });
  document.documentElement.appendChild(button);
})();
