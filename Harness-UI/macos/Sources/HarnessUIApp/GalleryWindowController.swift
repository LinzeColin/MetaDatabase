import AppKit
import WebKit

private final class GalleryWindow: NSWindow {
    var commandHandler: ((String) -> Bool)?

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if modifiers == .command,
           let key = event.charactersIgnoringModifiers?.lowercased(),
           commandHandler?(key) == true {
            return true
        }
        return super.performKeyEquivalent(with: event)
    }
}

final class GalleryWindowController: NSWindowController {
    private let webView: WKWebView
    private let port: UInt16

    init(port: UInt16) {
        self.port = port
        webView = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        let window = GalleryWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1220, height: 820),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        super.init(window: window)
        window.commandHandler = { [weak self] key in self?.handleCommand(key) ?? false }
        window.title = "Harness UI · 完整素材库"
        window.contentView = webView
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 760, height: 520)
        window.center()
        window.setFrameAutosaveName("HarnessUIFullLibrary")
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func show() {
        if webView.url == nil { loadLibrary() }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    private func loadLibrary() {
        guard let url = URL(string: "http://127.0.0.1:\(port)/") else { return }
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        webView.load(request)
    }

    private func handleCommand(_ key: String) -> Bool {
        switch key {
        case "r":
            loadLibrary()
            return true
        case "w":
            window?.performClose(nil)
            return true
        case "q":
            NSApp.terminate(nil)
            return true
        default:
            return false
        }
    }
}
