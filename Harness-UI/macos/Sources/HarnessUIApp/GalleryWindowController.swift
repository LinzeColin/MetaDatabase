import AppKit
import WebKit

final class GalleryWindowController: NSWindowController {
    private let webView: WKWebView
    private let port: UInt16

    init(port: UInt16) {
        self.port = port
        webView = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1220, height: 820),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        super.init(window: window)
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
        if webView.url == nil, let url = URL(string: "http://127.0.0.1:\(port)/") {
            var request = URLRequest(url: url)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            webView.load(request)
        }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }
}
