import Foundation

public final class HarnessStore: @unchecked Sendable {
    private let queue = DispatchQueue(label: "com.linzecolin.harnessui.store")
    private var catalogValue: Catalog = .empty
    private var stateValue = HarnessState()
    private var assetsValue: [String: URL] = [:]
    private let dataRoot: URL
    private let encoder: JSONEncoder
    private let decoder = JSONDecoder()

    public init(dataRoot: URL) {
        self.dataRoot = dataRoot
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        try? FileManager.default.createDirectory(at: dataRoot, withIntermediateDirectories: true)
        if let data = try? Data(contentsOf: stateFile), let state = try? decoder.decode(HarnessState.self, from: data) {
            stateValue = state
        }
        if let data = try? Data(contentsOf: catalogFile), let catalog = try? decoder.decode(Catalog.self, from: data) {
            catalogValue = catalog
        }
    }

    public var catalogFile: URL { dataRoot.appendingPathComponent("catalog.json") }
    public var stateFile: URL { dataRoot.appendingPathComponent("state.json") }
    public var configFile: URL { dataRoot.appendingPathComponent("config.json") }

    public func catalog() -> Catalog { queue.sync { catalogValue } }
    public func state() -> HarnessState { queue.sync { stateValue } }
    public func asset(for requestPath: String) -> URL? { queue.sync { assetsValue[requestPath] } }

    public func install(build: CatalogBuild) throws {
        try queue.sync {
            if catalogValue.count > 0 && build.catalog.count == 0 {
                throw NSError(
                    domain: "HarnessUI",
                    code: 2,
                    userInfo: [NSLocalizedDescriptionKey: "素材源未返回任何有效皮肤；已保留上一次的 \(catalogValue.count) 个素材。请检查 SMB 连接或所选目录。"]
                )
            }
            let previousGames = Set(catalogValue.entries.map(\.game))
            let nextGames = Set(build.catalog.entries.map(\.game))
            let missingGames = previousGames.subtracting(nextGames)
            if !missingGames.isEmpty {
                throw NSError(
                    domain: "HarnessUI",
                    code: 3,
                    userInfo: [NSLocalizedDescriptionKey: "素材源缺少既有游戏分区：\(missingGames.sorted().joined(separator: ", "))；已保留上一版目录。"]
                )
            }
            catalogValue = build.catalog
            assetsValue = build.assets
            stateValue = normalized(stateValue, catalog: catalogValue)
            stateValue.catalogGenerated = build.catalog.generated
            stateValue.updated = Int64(Date().timeIntervalSince1970 * 1000)
            try persistLocked()
        }
    }

    public func patch(_ values: [String: Any], now: Int64 = Int64(Date().timeIntervalSince1970 * 1000)) throws -> HarnessState {
        try queue.sync {
            if let mode = values["mode"] as? String { stateValue.mode = mode }
            if let selected = values["selected"] as? String { stateValue.selected = selected }
            if values["selected"] is NSNull { stateValue.selected = nil }
            if let interval = values["intervalMs"] as? NSNumber { stateValue.intervalMs = interval.intValue }
            if let hidden = values["hidden"] as? [String] { stateValue.hidden = hidden }
            stateValue.updated = now
            stateValue = normalized(stateValue, catalog: catalogValue)
            try persistStateLocked()
            return stateValue
        }
    }

    public func rotate(force: Bool, now: Int64 = Int64(Date().timeIntervalSince1970 * 1000)) throws -> HarnessState {
        try queue.sync {
            stateValue = normalized(stateValue, catalog: catalogValue)
            guard stateValue.mode == "rotate" else { return stateValue }
            guard force || now - stateValue.lastRotate >= Int64(stateValue.intervalMs) else { return stateValue }
            return try advanceLocked(now: now)
        }
    }

    public func next(now: Int64 = Int64(Date().timeIntervalSince1970 * 1000)) throws -> HarnessState {
        try queue.sync {
            stateValue = normalized(stateValue, catalog: catalogValue)
            return try advanceLocked(now: now)
        }
    }

    @discardableResult
    public func reloadFromDisk() -> Bool {
        queue.sync {
            let previousCatalog = catalogValue
            let previousState = stateValue
            if let data = try? Data(contentsOf: catalogFile), let catalog = try? decoder.decode(Catalog.self, from: data) {
                catalogValue = catalog
            }
            if let data = try? Data(contentsOf: stateFile), let state = try? decoder.decode(HarnessState.self, from: data) {
                stateValue = normalized(state, catalog: catalogValue)
            }
            return previousCatalog != catalogValue || previousState != stateValue
        }
    }

    public func jsonCatalog() throws -> Data { try queue.sync { try encoder.encode(catalogValue) } }
    public func jsonState() throws -> Data { try queue.sync { try encoder.encode(stateValue) } }

    private func normalized(_ input: HarnessState, catalog: Catalog) -> HarnessState {
        var state = input
        state.catalogGenerated = catalog.generated.isEmpty ? state.catalogGenerated : catalog.generated
        let ids = Set(catalog.entries.map(\.id))
        state.mode = state.mode == "rotate" ? "rotate" : "gallery"
        if state.intervalMs < 60_000 { state.intervalMs = 14_400_000 }
        state.hidden = Array(Set(state.hidden.filter(ids.contains))).sorted()
        state.cycle = state.cycle.filter { ids.contains($0) && !state.hidden.contains($0) }
        state.cursor = max(0, min(state.cursor, state.cycle.count))
        if let selected = state.selected, !ids.contains(selected) || state.hidden.contains(selected) { state.selected = nil }
        if state.selected == nil { state.selected = catalog.entries.first?.id }
        return state
    }

    private func advanceLocked(now: Int64) throws -> HarnessState {
        let hidden = Set(stateValue.hidden)
        let visible = catalogValue.entries.map(\.id).filter { !hidden.contains($0) }
        guard !visible.isEmpty else { return stateValue }

        for _ in 0..<2 {
            if stateValue.cycle.isEmpty || stateValue.cursor >= stateValue.cycle.count {
                stateValue.cycle = visible.shuffled()
                stateValue.cursor = 0
                if stateValue.cycle.count > 1, stateValue.cycle.first == stateValue.selected {
                    stateValue.cycle.append(stateValue.cycle.removeFirst())
                }
            }
            while stateValue.cursor < stateValue.cycle.count {
                let selected = stateValue.cycle[stateValue.cursor]
                stateValue.cursor += 1
                if visible.count > 1, selected == stateValue.selected { continue }
                stateValue.selected = selected
                stateValue.lastRotate = now
                stateValue.updated = now
                try persistStateLocked()
                return stateValue
            }
        }
        return stateValue
    }

    private func persistLocked() throws {
        try encoder.encode(catalogValue).write(to: catalogFile, options: .atomic)
        try persistStateLocked()
    }

    private func persistStateLocked() throws {
        try encoder.encode(stateValue).write(to: stateFile, options: .atomic)
    }
}
