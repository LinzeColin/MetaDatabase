import Foundation
import XCTest
@testable import HarnessUICore

final class CatalogBuilderTests: XCTestCase {
    func testBuildsExpectedCatalogAndAssetRoutes() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let variant = root.appendingPathComponent("原神/aino/skins/default", isDirectory: true)
        try FileManager.default.createDirectory(at: variant, withIntermediateDirectories: true)
        try Data("light".utf8).write(to: variant.appendingPathComponent("light.png"))
        try Data("dark".utf8).write(to: variant.appendingPathComponent("dark.png"))
        let build = buildCatalog(sourceRoot: root, labels: ["genshin/aino/default": Label(characterZh: "爱诺", variantZh: "默认")], now: Date(timeIntervalSince1970: 0))
        XCTAssertEqual(build.catalog.count, 1)
        XCTAssertEqual(build.catalog.entries.first?.fullLabel, "爱诺")
        XCTAssertTrue(build.catalog.entries.first?.light.contains("?v=") == true)
        XCTAssertNotNil(build.assets["/assets/%E5%8E%9F%E7%A5%9E/aino/default/light"])
        try FileManager.default.removeItem(at: root)
    }

    func testStateRejectsUnknownSelection() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = HarnessStore(dataRoot: root)
        let state = try store.patch(["selected": "missing"], now: 1)
        XCTAssertNil(state.selected)
        try FileManager.default.removeItem(at: root)
    }

    func testStoreKeepsPreviousCatalogWhenAGamePartitionDisappears() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = HarnessStore(dataRoot: root)
        func entry(_ id: String, _ game: String) -> CatalogEntry {
            CatalogEntry(id: id, game: game, gameName: game, character: id, variant: "default", characterZh: id, variantZh: "默认", label: id, fullLabel: id, light: "light", dark: "dark")
        }
        let complete = [entry("one", "genshin"), entry("two", "hsr")]
        try store.install(build: CatalogBuild(catalog: Catalog(version: 1, source: "smb", generated: "one", count: 2, entries: complete), assets: [:]))

        XCTAssertThrowsError(try store.install(build: CatalogBuild(
            catalog: Catalog(version: 1, source: "smb", generated: "two", count: 1, entries: [complete[0]]),
            assets: [:]
        )))
        XCTAssertEqual(store.catalog().count, 2)
        try FileManager.default.removeItem(at: root)
    }

    func testNextAdvancesWithoutChangingGalleryMode() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = HarnessStore(dataRoot: root)
        func entry(_ id: String) -> CatalogEntry {
            CatalogEntry(id: id, game: "genshin", gameName: "原神", character: id, variant: "default", characterZh: id, variantZh: "默认", label: id, fullLabel: id, light: "light", dark: "dark")
        }
        try store.install(build: CatalogBuild(catalog: Catalog(version: 1, source: "smb", generated: "one", count: 3, entries: [entry("one"), entry("two"), entry("three")]), assets: [:]))
        _ = try store.patch(["mode": "gallery", "selected": "one"], now: 1)
        let state = try store.next(now: 42)
        XCTAssertEqual(state.mode, "gallery")
        XCTAssertNotEqual(state.selected, "one")
        XCTAssertEqual(state.lastRotate, 42)
        try FileManager.default.removeItem(at: root)
    }

    func testSynchronizesSMBIntoLocalMasterWithoutDeletingLocalOnlySkins() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let source = root.appendingPathComponent("source", isDirectory: true)
        let master = root.appendingPathComponent("master", isDirectory: true)
        for (gameName, game) in harnessGameSlugs {
            let remote = source.appendingPathComponent("\(gameName)/character/skins/default", isDirectory: true)
            try FileManager.default.createDirectory(at: remote, withIntermediateDirectories: true)
            try Data("\(gameName)-light".utf8).write(to: remote.appendingPathComponent("light.png"))
            try Data("\(gameName)-dark".utf8).write(to: remote.appendingPathComponent("dark.png"))
            XCTAssertFalse(game.isEmpty)
        }
        let localOnly = master.appendingPathComponent("nte/local-only/default", isDirectory: true)
        try FileManager.default.createDirectory(at: localOnly, withIntermediateDirectories: true)
        try Data("local-light".utf8).write(to: localOnly.appendingPathComponent("light.png"))
        try Data("local-dark".utf8).write(to: localOnly.appendingPathComponent("dark.png"))

        let first = try synchronizeSourceToMaster(sourceRoot: source, masterRoot: master)
        XCTAssertEqual(first.sourceIds.count, harnessGameSlugs.count)
        XCTAssertEqual(first.deployedCount, harnessGameSlugs.count)
        let local = buildLocalCatalog(masterRoot: master)
        XCTAssertEqual(local.catalog.count, harnessGameSlugs.count + 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: localOnly.appendingPathComponent("light.png").path))

        let second = try synchronizeSourceToMaster(sourceRoot: source, masterRoot: master)
        XCTAssertEqual(second.deployedCount, 0)
        try FileManager.default.removeItem(at: root)
    }
}
