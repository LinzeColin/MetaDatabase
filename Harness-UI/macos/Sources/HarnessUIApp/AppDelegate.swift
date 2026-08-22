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
    private var stateSyncTimer: Timer?
    private var nextSkinHotKey: GlobalHotKey?
    private var galleryWindowController: GalleryWindowController?
    private var finishedLaunching = false
    private var pendingGalleryOpen = false
    private var refreshRunning = false
    private var usesExternalService = false
    private let refreshStatusLock = NSLock()
    private var refreshStatus: [String: Any] = ["status": "idle", "message": "尚未刷新", "updated": 0]
    private var webRoot: URL!
    private var labels: [String: Label] = [:]
    private var masterRoot: URL { dataRoot.appendingPathComponent("master", isDirectory: true) }
    private var sharedServiceLaunchAgent: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/com.harnessui.assets.plist")
    }
    private var syncHelperPort: UInt16 { configuration.port == UInt16.max ? configuration.port - 1 : configuration.port + 1 }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        loadResources()
        loadConfiguration()
        createMenu()
        do {
            nextSkinHotKey = try .commandShiftN { [weak self] in self?.nextSkin() }
        } catch {
            NSLog("[Harness UI] 无法注册 Cmd+Shift+N: %@", error.localizedDescription)
        }
        if sharedServiceAvailable() {
            usesExternalService = true
            _ = store.reloadFromDisk()
            do {
                try server.start(port: syncHelperPort) { [weak self] request in
                    self?.sourceSyncRoute(request) ?? HTTPResponse(status: 500)
                }
            } catch {
                showError("无法启动 SMB 同步 Helper", detail: error.localizedDescription)
            }
            stateSyncTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
                guard let self, self.store.reloadFromDisk() else { return }
                self.rebuildMenu()
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
                self?.refreshCatalog(showResult: false)
            }
        } else {
            let localBuild = buildLocalCatalog(masterRoot: masterRoot, labels: labels)
            if localBuild.catalog.count > 0 { try? store.install(build: localBuild) }
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
        finishedLaunching = true
        if pendingGalleryOpen { openGallery() }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        openGallery()
        return true
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        guard urls.contains(where: { $0.scheme?.lowercased() == "harnessui" }) else { return }
        openGallery()
    }

    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        refreshTimer?.invalidate()
        stateSyncTimer?.invalidate()
        nextSkinHotKey = nil
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
        if configuration.sourcePath.isEmpty { configuration.sourcePath = sharedServiceSourcePath() }
    }

    private func sharedServiceSourcePath() -> String {
        let fallback = URL(fileURLWithPath: "/Volumes/share/03_资料库/MetaData/HarnessUI", isDirectory: true).path
        guard let data = try? Data(contentsOf: sharedServiceLaunchAgent),
              let value = try? PropertyListSerialization.propertyList(from: data, options: [], format: nil),
              let object = value as? [String: Any],
              let arguments = object["ProgramArguments"] as? [String],
              let sourceIndex = arguments.firstIndex(of: "--source"),
              arguments.indices.contains(sourceIndex + 1) else { return fallback }
        return arguments[sourceIndex + 1]
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
        menu.addItem(withTitle: "打开完整素材库", action: #selector(openGallery), keyEquivalent: "o").target = self
        menu.addItem(withTitle: "选择 SMB 素材目录…", action: #selector(chooseSource), keyEquivalent: "").target = self
        menu.addItem(withTitle: "刷新素材目录", action: #selector(refreshFromMenu), keyEquivalent: "r").target = self
        let next = menu.addItem(withTitle: "换下一张", action: #selector(nextSkin), keyEquivalent: "n")
        next.keyEquivalentModifierMask = [.command, .shift]
        next.target = self
        let rotate = NSMenuItem(title: store.state().mode == "rotate" ? "停止轮播" : "开启轮播", action: #selector(toggleRotation), keyEquivalent: "")
        rotate.target = self
        menu.addItem(rotate)
        menu.addItem(.separator())
        menu.addItem(withTitle: "检查并下载更新…", action: #selector(openReleases), keyEquivalent: "").target = self
        menu.addItem(.separator())
        menu.addItem(withTitle: "退出 Harness UI", action: #selector(quit), keyEquivalent: "q").target = self
        statusItem?.menu = menu
    }

    @objc private func openGallery() {
        guard finishedLaunching else {
            pendingGalleryOpen = true
            return
        }
        pendingGalleryOpen = false
        let controller = galleryWindowController ?? GalleryWindowController(port: configuration.port)
        galleryWindowController = controller
        controller.show()
    }

    @objc private func openReleases() {
        NSWorkspace.shared.open(URL(string: "https://github.com/LinzeColin/MetaDatabase/releases?q=harness-ui-v")!)
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
        if usesExternalService {
            guard !refreshRunning else { return }
            refreshRunning = true
            statusItem?.button?.title = "HU…"
            let started = Int64(Date().timeIntervalSince1970 * 1000)
            postToSharedService(
                path: "/api/catalog/refresh",
                object: [:],
                failureTitle: "素材目录刷新失败",
                completion: { self.pollSharedRefresh(started: started, deadline: Date().addingTimeInterval(900), showResult: showResult) },
                failure: { self.finishSharedRefresh() }
            )
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
            do {
                let report = try synchronizeSourceToMaster(sourceRoot: root, masterRoot: self.masterRoot)
                let build = buildLocalCatalog(masterRoot: self.masterRoot, labels: self.labels)
                try self.store.install(build: build, forceGeneration: report.deployedCount > 0)
                let sourceIds = Set(report.sourceIds)
                let localIds = Set(build.catalog.entries.map(\.id))
                let missing = localIds.subtracting(sourceIds).count
                let missingGames = report.gameCounts.filter { $0.value == 0 }.map(\.key).sorted()
                let partial = missing > 0 || !missingGames.isEmpty
                let message = partial
                    ? "SMB 当前可用 \(sourceIds.count) 个，本地完整库 \(localIds.count) 个；SMB 缺少 \(missing) 个既有素材，已保留本地完整库；本次部署 \(report.deployedCount) 个"
                    : "SMB、本地与总目录均为 \(localIds.count) 个；本次部署 \(report.deployedCount) 个"
                DispatchQueue.main.async {
                    self.refreshRunning = false
                    self.setRefreshStatus(partial ? "partial" : "ready", message: message, details: [
                        "smbCount": sourceIds.count,
                        "localCount": localIds.count,
                        "catalogCount": build.catalog.count,
                        "deployedCount": report.deployedCount,
                        "missingFromSMB": missing,
                        "missingGames": missingGames,
                        "sourceOwner": "harness-app",
                    ])
                    self.statusItem?.button?.title = "HU"
                    self.rebuildMenu()
                    if showResult {
                        if partial { self.showError("SMB 素材未完整", detail: message) }
                        else { self.showInfo("素材目录已刷新", detail: message) }
                    }
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

    private func setRefreshStatus(_ status: String, message: String, details: [String: Any] = [:]) {
        refreshStatusLock.lock()
        refreshStatus = details.merging(["status": status, "message": message, "updated": Int64(Date().timeIntervalSince1970 * 1000)]) { _, latest in latest }
        refreshStatusLock.unlock()
    }

    private func sourceSyncRoute(_ request: HTTPRequest) -> HTTPResponse {
        guard request.method == "POST", request.path == "/api/source-sync" else {
            return HTTPResponse(status: request.method == "POST" ? 404 : 405)
        }
        do {
            let source = URL(fileURLWithPath: configuration.sourcePath, isDirectory: true)
            let report = try synchronizeSourceToMaster(sourceRoot: source, masterRoot: masterRoot)
            let body = try JSONEncoder().encode(report)
            return HTTPResponse(contentType: "application/json; charset=utf-8", body: body, headers: ["Cache-Control": "no-store"])
        } catch {
            let body = (try? JSONSerialization.data(withJSONObject: ["message": error.localizedDescription])) ?? Data()
            return HTTPResponse(status: 500, contentType: "application/json; charset=utf-8", body: body, headers: ["Cache-Control": "no-store"])
        }
    }

    private func refreshStatusResponse() -> HTTPResponse {
        refreshStatusLock.lock()
        let value = refreshStatus
        refreshStatusLock.unlock()
        guard let data = try? JSONSerialization.data(withJSONObject: value) else { return HTTPResponse(status: 500) }
        return HTTPResponse(contentType: "application/json; charset=utf-8", body: data, headers: ["Cache-Control": "no-store"])
    }

    private func pollSharedRefresh(started: Int64, deadline: Date, showResult: Bool) {
        guard let url = URL(string: "http://127.0.0.1:\(configuration.port)/refresh-status.json") else {
            finishSharedRefresh()
            return
        }
        var request = URLRequest(url: url, timeoutInterval: 5)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self else { return }
                let httpStatus = (response as? HTTPURLResponse)?.statusCode ?? 0
                let object = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
                let status = object?["status"] as? String ?? ""
                let message = object?["message"] as? String ?? "素材目录仍在扫描"
                let updated = (object?["updated"] as? NSNumber)?.int64Value ?? 0
                if error == nil, (200...299).contains(httpStatus), updated >= started {
                    if status == "ready" || status == "partial" {
                        self.finishSharedRefresh()
                        _ = self.store.reloadFromDisk()
                        self.rebuildMenu()
                        if showResult {
                            if status == "partial" { self.showError("SMB 素材未完整", detail: message) }
                            else { self.showInfo("素材目录已刷新", detail: message) }
                        }
                        return
                    }
                    if status == "failed" {
                        self.finishSharedRefresh()
                        if showResult { self.showError("刷新失败", detail: message) }
                        return
                    }
                }
                guard Date() < deadline else {
                    self.finishSharedRefresh()
                    if showResult { self.showError("刷新超时", detail: message) }
                    return
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                    self.pollSharedRefresh(started: started, deadline: deadline, showResult: showResult)
                }
            }
        }.resume()
    }

    private func finishSharedRefresh() {
        refreshRunning = false
        statusItem?.button?.title = "HU"
    }

    @objc private func nextSkin() {
        if usesExternalService {
            postToSharedService(path: "/api/next", object: [:], failureTitle: "切换失败")
            return
        }
        do { _ = try store.next(); rebuildMenu() }
        catch { showError("切换失败", detail: error.localizedDescription) }
    }

    @objc private func toggleRotation() {
        let next = store.state().mode == "rotate" ? "gallery" : "rotate"
        if usesExternalService {
            postToSharedService(path: "/api/state", object: ["mode": next], failureTitle: "模式切换失败")
            return
        }
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
        if request.method == "POST", request.path == "/api/next" {
            do {
                _ = try store.next()
                DispatchQueue.main.async { [weak self] in self?.rebuildMenu() }
                return jsonResponse { try store.jsonState() }
            }
            catch { return HTTPResponse(status: 500) }
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

    private func sharedServiceAvailable() -> Bool {
        let configured = FileManager.default.fileExists(atPath: sharedServiceLaunchAgent.path)
        let attempts = configured ? 12 : 1
        for attempt in 0..<attempts {
            if probeSharedService() { return true }
            if attempt + 1 < attempts { Thread.sleep(forTimeInterval: 0.5) }
        }
        return false
    }

    private func probeSharedService() -> Bool {
        guard let url = URL(string: "http://127.0.0.1:\(configuration.port)/state.json") else { return false }
        var request = URLRequest(url: url, timeoutInterval: 0.5)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let semaphore = DispatchSemaphore(value: 0)
        let resultLock = NSLock()
        var available = false
        URLSession.shared.dataTask(with: request) { data, response, _ in
            let valid = (response as? HTTPURLResponse)?.statusCode == 200 && data.flatMap { try? JSONDecoder().decode(HarnessState.self, from: $0) } != nil
            resultLock.lock()
            available = valid
            resultLock.unlock()
            semaphore.signal()
        }.resume()
        _ = semaphore.wait(timeout: .now() + 0.75)
        resultLock.lock()
        defer { resultLock.unlock() }
        return available
    }

    private func postToSharedService(
        path: String,
        object: [String: Any],
        failureTitle: String,
        completion: (() -> Void)? = nil,
        failure: (() -> Void)? = nil
    ) {
        guard let url = URL(string: "http://127.0.0.1:\(configuration.port)\(path)"),
              let body = try? JSONSerialization.data(withJSONObject: object) else {
            showError(failureTitle, detail: "无法生成本机同步请求")
            failure?()
            return
        }
        var request = URLRequest(url: url, timeoutInterval: 5)
        request.httpMethod = "POST"
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        URLSession.shared.dataTask(with: request) { [weak self] _, response, error in
            DispatchQueue.main.async {
                guard let self else { return }
                let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                guard error == nil, (200...299).contains(status) else {
                    self.showError(failureTitle, detail: error?.localizedDescription ?? "本机素材服务返回 HTTP \(status)")
                    failure?()
                    return
                }
                _ = self.store.reloadFromDisk()
                self.rebuildMenu()
                completion?()
            }
        }.resume()
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
