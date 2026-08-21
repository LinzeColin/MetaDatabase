import AppKit
import Foundation
import HarnessUICore

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let dataRoot = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".harness-ui", isDirectory: true)
    private lazy var store = HarnessStore(dataRoot: dataRoot)
    private let server = LoopbackHTTPServer()
    private var configuration = HarnessConfiguration()
    private var statusItem: NSStatusItem?
    private var timer: Timer?
    private var refreshTimer: Timer?
    private var refreshRunning = false
    private let refreshStatusLock = NSLock()
    private var refreshStatus: [String: Any] = ["status": "idle", "message": "尚未刷新", "updated": 0]
    private var webRoot: URL!
    private var labels: [String: Label] = [:]

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        loadResources()
        loadConfiguration()
        createMenu()
        do {
            try server.start(port: configuration.port) { [weak self] request in
                self?.route(request) ?? HTTPResponse(status: 500)
            }
        } catch {
            showError("无法启动本机素材服务", detail: error.localizedDescription)
        }
        if !configuration.sourcePath.isEmpty { refreshCatalog(showResult: false) }
        scheduleRotation()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 900, repeats: true) { [weak self] _ in
            self?.refreshCatalog(showResult: false)
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        refreshTimer?.invalidate()
        server.stop()
    }

    private func loadResources() {
        if let resourceRoot = Bundle.main.resourceURL,
           FileManager.default.fileExists(atPath: resourceRoot.appendingPathComponent("web/index.html").path) {
            webRoot = resourceRoot.appendingPathComponent("web", isDirectory: true)
            if let data = try? Data(contentsOf: resourceRoot.appendingPathComponent("labels.seed.json")) {
                labels = (try? JSONDecoder().decode([String: Label].self, from: data)) ?? [:]
            }
        } else {
            let configured = ProcessInfo.processInfo.environment["HARNESS_UI_WEB_ROOT"]
            webRoot = URL(fileURLWithPath: configured ?? "../web", relativeTo: URL(fileURLWithPath: FileManager.default.currentDirectoryPath)).standardizedFileURL
            let labelsURL = webRoot.deletingLastPathComponent().appendingPathComponent("config/labels.seed.json")
            if let data = try? Data(contentsOf: labelsURL) { labels = (try? JSONDecoder().decode([String: Label].self, from: data)) ?? [:] }
        }
    }

    private func loadConfiguration() {
        if let data = try? Data(contentsOf: store.configFile), let value = try? JSONDecoder().decode(HarnessConfiguration.self, from: data) {
            configuration = value
        }
    }

    private func saveConfiguration() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        try encoder.encode(configuration).write(to: store.configFile, options: .atomic)
    }

    private func createMenu() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "HU"
        item.button?.toolTip = "Harness UI"
        statusItem = item
        rebuildMenu()
    }

    private func rebuildMenu() {
        let menu = NSMenu()
        let selected = store.catalog().entries.first { $0.id == store.state().selected }
        let current = NSMenuItem(title: "当前：\(selected?.fullLabel ?? "未选择")", action: nil, keyEquivalent: "")
        current.isEnabled = false
        menu.addItem(current)
        let count = NSMenuItem(title: "素材库：\(store.catalog().count) 个变体", action: nil, keyEquivalent: "")
        count.isEnabled = false
        menu.addItem(count)
        menu.addItem(.separator())
        menu.addItem(withTitle: "打开角色库", action: #selector(openGallery), keyEquivalent: "o").target = self
        menu.addItem(withTitle: "选择 SMB 素材目录…", action: #selector(chooseSource), keyEquivalent: "").target = self
        menu.addItem(withTitle: "刷新素材目录", action: #selector(refreshFromMenu), keyEquivalent: "r").target = self
        menu.addItem(withTitle: "换下一张", action: #selector(nextSkin), keyEquivalent: "n").target = self
        let rotate = NSMenuItem(title: store.state().mode == "rotate" ? "停止轮播" : "开启轮播", action: #selector(toggleRotation), keyEquivalent: "")
        rotate.target = self
        menu.addItem(rotate)
        menu.addItem(.separator())
        menu.addItem(withTitle: "退出 Harness UI", action: #selector(quit), keyEquivalent: "q").target = self
        statusItem?.menu = menu
    }

    @objc private func openGallery() {
        NSWorkspace.shared.open(URL(string: "http://127.0.0.1:\(configuration.port)/")!)
    }

    @objc private func chooseSource() {
        let panel = NSOpenPanel()
        panel.title = "选择 HarnessUI 素材根目录"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        NSApp.activate(ignoringOtherApps: true)
        guard panel.runModal() == .OK, let selected = panel.url else { return }
        configuration.sourcePath = selected.path
        do { try saveConfiguration(); refreshCatalog(showResult: true) }
        catch { showError("无法保存素材目录", detail: error.localizedDescription) }
    }

    @objc private func refreshFromMenu() { refreshCatalog(showResult: true) }

    private func refreshCatalog(showResult: Bool) {
        if !Thread.isMainThread {
            DispatchQueue.main.async { [weak self] in self?.refreshCatalog(showResult: showResult) }
            return
        }
        guard !refreshRunning else { return }
        guard !configuration.sourcePath.isEmpty else {
            setRefreshStatus("failed", message: "尚未选择素材目录")
            if showResult { showError("尚未选择素材目录", detail: configuration.smbURL) }
            return
        }
        refreshRunning = true
        setRefreshStatus("running", message: "正在读取 SMB 素材目录")
        statusItem?.button?.title = "HU…"
        let root = URL(fileURLWithPath: configuration.sourcePath, isDirectory: true)
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let build = buildCatalog(sourceRoot: root, labels: self.labels)
            do {
                try self.store.install(build: build)
                DispatchQueue.main.async {
                    self.refreshRunning = false
                    self.setRefreshStatus("ready", message: "已同步 \(build.catalog.count) 个变体")
                    self.statusItem?.button?.title = "HU"
                    self.rebuildMenu()
                    if showResult { self.showInfo("素材目录已刷新", detail: "共 \(build.catalog.count) 个变体") }
                }
            } catch {
                DispatchQueue.main.async {
                    self.refreshRunning = false
                    self.setRefreshStatus("failed", message: error.localizedDescription)
                    self.statusItem?.button?.title = "HU"
                    if showResult { self.showError("刷新失败", detail: error.localizedDescription) }
                }
            }
        }
    }

    private func setRefreshStatus(_ status: String, message: String) {
        refreshStatusLock.lock()
        refreshStatus = ["status": status, "message": message, "updated": Int64(Date().timeIntervalSince1970 * 1000)]
        refreshStatusLock.unlock()
    }

    private func refreshStatusResponse() -> HTTPResponse {
        refreshStatusLock.lock()
        let value = refreshStatus
        refreshStatusLock.unlock()
        guard let data = try? JSONSerialization.data(withJSONObject: value) else { return HTTPResponse(status: 500) }
        return HTTPResponse(contentType: "application/json; charset=utf-8", body: data, headers: ["Cache-Control": "no-store"])
    }

    @objc private func nextSkin() {
        do { _ = try store.patch(["mode": "rotate"]); _ = try store.rotate(force: true); rebuildMenu() }
        catch { showError("切换失败", detail: error.localizedDescription) }
    }

    @objc private func toggleRotation() {
        let next = store.state().mode == "rotate" ? "gallery" : "rotate"
        do { _ = try store.patch(["mode": next]); if next == "rotate" { _ = try store.rotate(force: true) }; scheduleRotation(); rebuildMenu() }
        catch { showError("模式切换失败", detail: error.localizedDescription) }
    }

    private func scheduleRotation() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            guard let self, self.store.state().mode == "rotate" else { return }
            do { let before = self.store.state().selected; let after = try self.store.rotate(force: false).selected; if before != after { self.rebuildMenu() } }
            catch { }
        }
    }

    private func route(_ request: HTTPRequest) -> HTTPResponse {
        if request.method == "OPTIONS" { return HTTPResponse(status: 204, headers: ["Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type"]) }
        if request.method == "GET", request.path == "/catalog.json" { return jsonResponse { try store.jsonCatalog() } }
        if request.method == "GET", request.path == "/state.json" { return jsonResponse { try store.jsonState() } }
        if request.method == "GET", request.path == "/refresh-status.json" { return refreshStatusResponse() }
        if request.method == "POST", request.path == "/api/catalog/refresh" {
            DispatchQueue.main.async { [weak self] in self?.refreshCatalog(showResult: false) }
            let body = Data("{\"status\":\"accepted\"}".utf8)
            return HTTPResponse(status: 202, contentType: "application/json; charset=utf-8", body: body, headers: ["Cache-Control": "no-store"])
        }
        if request.method == "POST", request.path == "/api/state" {
            guard let object = try? JSONSerialization.jsonObject(with: request.body) as? [String: Any] else { return HTTPResponse(status: 400) }
            do {
                let patched = try store.patch(object)
                if object["mode"] as? String == "rotate", patched.mode == "rotate" { _ = try store.rotate(force: true) }
                DispatchQueue.main.async { [weak self] in self?.rebuildMenu() }
                return jsonResponse { try store.jsonState() }
            }
            catch { return HTTPResponse(status: 500) }
        }
        if request.method == "GET", let asset = store.asset(for: request.path), let data = try? Data(contentsOf: asset) {
            return HTTPResponse(contentType: "image/png", body: data, headers: ["Cache-Control": "public, max-age=86400"])
        }
        if request.method == "GET" {
            let files = ["/": ("index.html", "text/html; charset=utf-8"), "/app.css": ("app.css", "text/css; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8")]
            if let (name, type) = files[request.path], let data = try? Data(contentsOf: webRoot.appendingPathComponent(name)) {
                return HTTPResponse(contentType: type, body: data, headers: ["Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'self' http://127.0.0.1:* http://localhost:*"])
            }
        }
        return HTTPResponse(status: request.method == "GET" ? 404 : 405)
    }

    private func jsonResponse(_ body: () throws -> Data) -> HTTPResponse {
        do { return HTTPResponse(contentType: "application/json; charset=utf-8", body: try body(), headers: ["Cache-Control": "no-store"]) }
        catch { return HTTPResponse(status: 500) }
    }

    private func showInfo(_ message: String, detail: String) { showAlert(style: .informational, message: message, detail: detail) }
    private func showError(_ message: String, detail: String) { showAlert(style: .warning, message: message, detail: detail) }
    private func showAlert(style: NSAlert.Style, message: String, detail: String) {
        DispatchQueue.main.async {
            let alert = NSAlert(); alert.alertStyle = style; alert.messageText = message; alert.informativeText = detail
            NSApp.activate(ignoringOtherApps: true); alert.runModal()
        }
    }

    @objc private func quit() { NSApp.terminate(nil) }
}
