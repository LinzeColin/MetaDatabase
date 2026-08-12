"use strict";

const http = require("http");
const crypto = require("crypto");
const { Plugin, PluginSettingTab, Setting, Notice, normalizePath, TFile } = require("obsidian");

const DEFAULT_SETTINGS = Object.freeze({
  enabled: true,
  port: 27123,
  token: "",
  baseFolder: "Social Archive",
  maxBytes: 20 * 1024 * 1024
});

class SocialArchivePlugin extends Plugin {
  async onload() {
    this.settings = { ...DEFAULT_SETTINGS, ...(await this.loadData()) };
    let settingsChanged = false;
    if (this.settings.port !== DEFAULT_SETTINGS.port) {
      this.settings.port = DEFAULT_SETTINGS.port;
      settingsChanged = true;
    }
    const maxBytes = Number(this.settings.maxBytes);
    const boundedMaxBytes = Number.isFinite(maxBytes) && maxBytes > 0
      ? Math.min(Math.floor(maxBytes), DEFAULT_SETTINGS.maxBytes)
      : DEFAULT_SETTINGS.maxBytes;
    if (this.settings.maxBytes !== boundedMaxBytes) {
      this.settings.maxBytes = boundedMaxBytes;
      settingsChanged = true;
    }
    try {
      const baseFolder = this.safeBaseFolder(this.settings.baseFolder);
      if (baseFolder !== this.settings.baseFolder) {
        this.settings.baseFolder = baseFolder;
        settingsChanged = true;
      }
    } catch (_) {
      this.settings.baseFolder = DEFAULT_SETTINGS.baseFolder;
      settingsChanged = true;
    }
    if (!this.settings.token) {
      this.settings.token = crypto.randomBytes(32).toString("base64url");
      settingsChanged = true;
    }
    if (settingsChanged) await this.saveSettings();
    this.addSettingTab(new SocialArchiveSettingTab(this.app, this));
    this.addCommand({
      id: "show-connection-token",
      name: "显示连接令牌",
      callback: () => new Notice(`Social Archive 端口 ${this.settings.port}；令牌已在插件设置中显示。`, 7000)
    });
    if (this.settings.enabled) await this.startServer();
  }

  async onunload() {
    await this.stopServer();
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  async restartServer() {
    await this.stopServer();
    if (this.settings.enabled) await this.startServer();
  }

  async stopServer() {
    if (!this.server) return;
    const current = this.server;
    this.server = null;
    await new Promise(resolve => current.close(() => resolve()));
  }

  authorized(request) {
    const supplied = String(request.headers.authorization || "").replace(/^Bearer\s+/i, "").trim();
    const expected = String(this.settings.token || "");
    const suppliedBytes = Buffer.from(supplied, "utf8");
    const expectedBytes = Buffer.from(expected, "utf8");
    if (!suppliedBytes.length || !expectedBytes.length || suppliedBytes.length !== expectedBytes.length) return false;
    return crypto.timingSafeEqual(suppliedBytes, expectedBytes);
  }

  send(response, status, body, contentType = "application/json; charset=utf-8") {
    response.writeHead(status, {
      "Content-Type": contentType,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    });
    response.end(typeof body === "string" ? body : JSON.stringify(body));
  }

  safeBaseFolder(value = this.settings.baseFolder) {
    const raw = String(value || DEFAULT_SETTINGS.baseFolder).trim();
    if (!raw || raw.includes("\0") || /^(?:[\\/]|[A-Za-z]:[\\/])/.test(raw)) throw new Error("保存目录不安全");
    if (raw.split(/[\\/]+/).includes("..")) throw new Error("保存目录不安全");
    const normalized = normalizePath(raw.replace(/\\/g, "/"));
    if (!normalized || normalized === "." || normalized === ".." || normalized.split("/").includes("..")) throw new Error("保存目录不安全");
    return normalized;
  }

  safeTarget(encodedPath) {
    let decoded;
    try { decoded = decodeURIComponent(String(encodedPath || "")); }
    catch (_) { throw new Error("路径编码无效"); }
    if (!decoded || decoded.includes("\0") || /^(?:[\\/]|[A-Za-z]:[\\/])/.test(decoded)) throw new Error("路径不安全");
    if (decoded.split(/[\\/]+/).includes("..")) throw new Error("路径不安全");
    const normalized = normalizePath(decoded.replace(/\\/g, "/"));
    if (!normalized || normalized === "." || normalized === ".." || normalized.split("/").includes("..")) throw new Error("路径不安全");
    const base = this.safeBaseFolder();
    const target = normalized.startsWith(`${base}/`) || normalized === base ? normalized : normalizePath(`${base}/${normalized}`);
    if (!target.endsWith(".md")) throw new Error("只允许写入 Markdown 文件");
    return target;
  }

  async ensureFolder(path) {
    const parts = normalizePath(path).split("/").slice(0, -1);
    let current = "";
    for (const part of parts) {
      current = current ? `${current}/${part}` : part;
      if (!this.app.vault.getAbstractFileByPath(current)) {
        try { await this.app.vault.createFolder(current); } catch (error) {
          if (!this.app.vault.getAbstractFileByPath(current)) throw error;
        }
      }
    }
  }

  async writeMarkdown(path, body) {
    await this.ensureFolder(path);
    const existing = this.app.vault.getAbstractFileByPath(path);
    if (existing instanceof TFile) {
      if (await this.app.vault.read(existing) === body) return { status: "noop", path };
      await this.app.vault.modify(existing, body);
    }
    else if (existing) throw new Error("目标路径不是文件");
    else await this.app.vault.create(path, body);
    return { status: "done", path };
  }

  async handle(request, response) {
    if (!this.authorized(request)) return this.send(response, 401, { status: "unauthorized" });
    if (request.method === "GET" && request.url === "/health") {
      return this.send(response, 200, { status: "ok", product: "Social Archive", version: "0.0.0.7", port: this.settings.port });
    }
    if (request.method !== "PUT" || request.url !== "/vault") return this.send(response, 404, { status: "not_found" });
    if (!String(request.headers["content-type"] || "").toLowerCase().startsWith("text/markdown")) {
      return this.send(response, 415, { status: "markdown_required" });
    }
    let size = 0;
    const chunks = [];
    for await (const chunk of request) {
      size += chunk.length;
      if (size > this.settings.maxBytes) return this.send(response, 413, { status: "too_large" });
      chunks.push(chunk);
    }
    try {
      const target = this.safeTarget(request.headers["x-social-archive-path"]);
      this.send(response, 200, await this.writeMarkdown(target, Buffer.concat(chunks).toString("utf8")));
    } catch (error) {
      this.send(response, 422, { status: "invalid", message: String(error?.message || error) });
    }
  }

  async startServer() {
    if (this.server) return;
    this.server = http.createServer((request, response) => {
      this.handle(request, response).catch(error => this.send(response, 500, { status: "error", message: String(error?.message || error) }));
    });
    await new Promise((resolve, reject) => {
      this.server.once("error", reject);
      this.server.listen(this.settings.port, "127.0.0.1", () => {
        this.server.off("error", reject);
        resolve();
      });
    });
  }
}

class SocialArchiveSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "Social Archive 自动导入" });
    containerEl.createEl("p", { text: "服务只监听 127.0.0.1，必须携带令牌，不会建立系统常驻任务。关闭 Obsidian 后服务自动停止。" });

    new Setting(containerEl).setName("启用本机导入").setDesc("允许浏览器扩展写入当前 Vault。")
      .addToggle(toggle => toggle.setValue(this.plugin.settings.enabled).onChange(async value => {
        this.plugin.settings.enabled = value;
        await this.plugin.saveSettings();
        await this.plugin.restartServer();
      }));

    containerEl.createEl("p", { text: "端口固定为 127.0.0.1:27123；浏览器扩展只会请求这个 loopback 地址。" });

    new Setting(containerEl).setName("连接令牌").setDesc("复制到 Social Archive 扩展设置；不要发送给其他人。")
      .addText(text => text.setValue(this.plugin.settings.token).onChange(async value => {
        this.plugin.settings.token = value.trim();
        await this.plugin.saveSettings();
      }))
      .addButton(button => button.setButtonText("重新生成").onClick(async () => {
        this.plugin.settings.token = crypto.randomBytes(32).toString("base64url");
        await this.plugin.saveSettings();
        this.display();
      }));

    new Setting(containerEl).setName("保存目录").setDesc("所有自动导入都限制在这个目录下。")
      .addText(text => text.setValue(this.plugin.settings.baseFolder).onChange(async value => {
        try {
          this.plugin.settings.baseFolder = this.plugin.safeBaseFolder(value || DEFAULT_SETTINGS.baseFolder);
          await this.plugin.saveSettings();
        } catch (_) {
          new Notice("保存目录只能是当前 Vault 内的普通子目录。");
          this.display();
        }
      }));
  }
}

module.exports = SocialArchivePlugin;
