import Foundation

private let segmentAllowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))

private func encodedSegment(_ value: String) -> String {
    value.addingPercentEncoding(withAllowedCharacters: segmentAllowed) ?? value
}

private func childDirectories(_ root: URL, fileManager: FileManager) -> [URL] {
    let keys: Set<URLResourceKey> = [.isDirectoryKey]
    let children = (try? fileManager.contentsOfDirectory(at: root, includingPropertiesForKeys: Array(keys), options: [.skipsHiddenFiles])) ?? []
    return children.filter { (try? $0.resourceValues(forKeys: keys).isDirectory) == true }
        .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
}

private func requiredChildDirectories(_ root: URL, fileManager: FileManager) throws -> [URL] {
    let keys: Set<URLResourceKey> = [.isDirectoryKey]
    let children = try fileManager.contentsOfDirectory(at: root, includingPropertiesForKeys: Array(keys), options: [.skipsHiddenFiles])
    return children.filter { (try? $0.resourceValues(forKeys: keys).isDirectory) == true }
        .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
}

private func metaLabels(_ file: URL) -> Label? {
    guard let data = try? Data(contentsOf: file),
          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let character = object["characterZh"] as? String,
          let variant = object["variantZh"] as? String else { return nil }
    return Label(characterZh: character, variantZh: variant)
}

private func copyRequired(_ source: URL, _ destination: URL, fileManager: FileManager) -> Bool {
    guard fileManager.fileExists(atPath: destination.path) else { return true }
    let keys: Set<URLResourceKey> = [.fileSizeKey, .contentModificationDateKey]
    guard let sourceValues = try? source.resourceValues(forKeys: keys),
          let destinationValues = try? destination.resourceValues(forKeys: keys) else { return true }
    if sourceValues.fileSize != destinationValues.fileSize { return true }
    guard let sourceDate = sourceValues.contentModificationDate,
          let destinationDate = destinationValues.contentModificationDate else { return false }
    return sourceDate > destinationDate
}

@discardableResult
private func copyAtomically(_ source: URL, to destination: URL, fileManager: FileManager) throws -> Bool {
    guard copyRequired(source, destination, fileManager: fileManager) else { return false }
    try fileManager.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
    let staged = destination.deletingLastPathComponent()
        .appendingPathComponent(".\(destination.lastPathComponent).\(UUID().uuidString).sync")
    do {
        try fileManager.copyItem(at: source, to: staged)
        if fileManager.fileExists(atPath: destination.path) {
            _ = try fileManager.replaceItemAt(destination, withItemAt: staged)
        } else {
            try fileManager.moveItem(at: staged, to: destination)
        }
    } catch {
        try? fileManager.removeItem(at: staged)
        throw error
    }
    return true
}

public func synchronizeSourceToMaster(
    sourceRoot: URL,
    masterRoot: URL,
    fileManager: FileManager = .default
) throws -> SourceSyncReport {
    guard fileManager.fileExists(atPath: sourceRoot.path) else {
        throw NSError(domain: "HarnessUI", code: 20, userInfo: [NSLocalizedDescriptionKey: "SMB 素材目录不可达：\(sourceRoot.path)"])
    }
    _ = try requiredChildDirectories(sourceRoot, fileManager: fileManager)
    try fileManager.createDirectory(at: masterRoot, withIntermediateDirectories: true)
    var sourceIds: [String] = []
    var gameCounts = Dictionary(uniqueKeysWithValues: harnessGameSlugs.values.map { ($0, 0) })
    var changed: Set<String> = []

    for gameName in harnessGameSlugs.keys.sorted() {
        guard let game = harnessGameSlugs[gameName] else { continue }
        let gameRoot = sourceRoot.appendingPathComponent(gameName, isDirectory: true)
        guard fileManager.fileExists(atPath: gameRoot.path) else { continue }
        for characterRoot in try requiredChildDirectories(gameRoot, fileManager: fileManager) {
            let character = characterRoot.lastPathComponent
            let skinsRoot = characterRoot.appendingPathComponent("skins", isDirectory: true)
            guard fileManager.fileExists(atPath: skinsRoot.path) else { continue }
            for variantRoot in try requiredChildDirectories(skinsRoot, fileManager: fileManager) {
                let variant = variantRoot.lastPathComponent
                let light = variantRoot.appendingPathComponent("light.png")
                let dark = variantRoot.appendingPathComponent("dark.png")
                guard fileManager.fileExists(atPath: light.path), fileManager.fileExists(atPath: dark.path) else { continue }
                let identifier = "\(game)/\(character)/\(variant)"
                sourceIds.append(identifier)
                gameCounts[game, default: 0] += 1
                let destination = masterRoot
                    .appendingPathComponent(game, isDirectory: true)
                    .appendingPathComponent(character, isDirectory: true)
                    .appendingPathComponent(variant, isDirectory: true)
                if try copyAtomically(light, to: destination.appendingPathComponent("light.png"), fileManager: fileManager) { changed.insert(identifier) }
                if try copyAtomically(dark, to: destination.appendingPathComponent("dark.png"), fileManager: fileManager) { changed.insert(identifier) }
                let meta = variantRoot.appendingPathComponent("meta.json")
                if fileManager.fileExists(atPath: meta.path),
                   try copyAtomically(meta, to: destination.appendingPathComponent("meta.json"), fileManager: fileManager) { changed.insert(identifier) }
            }
        }
    }
    return SourceSyncReport(sourceIds: sourceIds.sorted(), gameCounts: gameCounts, deployedCount: changed.count)
}

public func buildLocalCatalog(
    masterRoot: URL,
    baseURL: String = "http://127.0.0.1:3099",
    labels: [String: Label] = [:],
    now: Date = Date(),
    fileManager: FileManager = .default
) -> CatalogBuild {
    let formatter = ISO8601DateFormatter()
    let generated = formatter.string(from: now)
    let revision = encodedSegment(generated)
    var entries: [CatalogEntry] = []
    var assets: [String: URL] = [:]
    for gameName in harnessGameSlugs.keys.sorted() {
        guard let game = harnessGameSlugs[gameName] else { continue }
        let gameRoot = masterRoot.appendingPathComponent(game, isDirectory: true)
        for characterRoot in childDirectories(gameRoot, fileManager: fileManager) {
            let character = characterRoot.lastPathComponent
            for variantRoot in childDirectories(characterRoot, fileManager: fileManager) {
                let variant = variantRoot.lastPathComponent
                let lightFile = variantRoot.appendingPathComponent("light.png")
                let darkFile = variantRoot.appendingPathComponent("dark.png")
                guard fileManager.fileExists(atPath: lightFile.path), fileManager.fileExists(atPath: darkFile.path) else { continue }
                let id = "\(game)/\(character)/\(variant)"
                let label = labels[id] ?? metaLabels(variantRoot.appendingPathComponent("meta.json"))
                let characterZh = label?.characterZh ?? character
                let variantZh = label?.variantZh ?? (variant == "default" ? "默认" : variant)
                let prefix = "/assets/\(encodedSegment(gameName))/\(encodedSegment(character))/\(encodedSegment(variant))"
                let lightPath = "\(prefix)/light"
                let darkPath = "\(prefix)/dark"
                assets[lightPath] = lightFile
                assets[darkPath] = darkFile
                entries.append(CatalogEntry(
                    id: id,
                    game: game,
                    gameName: gameName,
                    character: character,
                    variant: variant,
                    characterZh: characterZh,
                    variantZh: variantZh,
                    label: characterZh,
                    fullLabel: variant == "default" ? characterZh : "\(characterZh) · \(variantZh)",
                    light: "\(baseURL)\(lightPath)?v=\(revision)",
                    dark: "\(baseURL)\(darkPath)?v=\(revision)"
                ))
            }
        }
    }
    entries.sort { $0.fullLabel.localizedStandardCompare($1.fullLabel) == .orderedAscending }
    let catalog = Catalog(version: 1, source: "local-master", generated: generated, count: entries.count, entries: entries)
    return CatalogBuild(catalog: catalog, assets: assets)
}

public func buildCatalog(
    sourceRoot: URL,
    baseURL: String = "http://127.0.0.1:3099",
    labels: [String: Label] = [:],
    now: Date = Date(),
    fileManager: FileManager = .default
) -> CatalogBuild {
    let formatter = ISO8601DateFormatter()
    let generated = formatter.string(from: now)
    let revision = encodedSegment(generated)
    var entries: [CatalogEntry] = []
    var assets: [String: URL] = [:]
    for gameName in harnessGameSlugs.keys.sorted() {
        guard let game = harnessGameSlugs[gameName] else { continue }
        let gameRoot = sourceRoot.appendingPathComponent(gameName, isDirectory: true)
        for characterRoot in childDirectories(gameRoot, fileManager: fileManager) {
            let character = characterRoot.lastPathComponent
            let skinsRoot = characterRoot.appendingPathComponent("skins", isDirectory: true)
            for variantRoot in childDirectories(skinsRoot, fileManager: fileManager) {
                let variant = variantRoot.lastPathComponent
                let lightFile = variantRoot.appendingPathComponent("light.png")
                let darkFile = variantRoot.appendingPathComponent("dark.png")
                guard fileManager.fileExists(atPath: lightFile.path), fileManager.fileExists(atPath: darkFile.path) else { continue }
                let id = "\(game)/\(character)/\(variant)"
                let label = labels[id] ?? metaLabels(variantRoot.appendingPathComponent("meta.json"))
                let characterZh = label?.characterZh ?? character
                let variantZh = label?.variantZh ?? (variant == "default" ? "默认" : variant)
                let prefix = "/assets/\(encodedSegment(gameName))/\(encodedSegment(character))/\(encodedSegment(variant))"
                let lightPath = "\(prefix)/light"
                let darkPath = "\(prefix)/dark"
                assets[lightPath] = lightFile
                assets[darkPath] = darkFile
                entries.append(CatalogEntry(
                    id: id,
                    game: game,
                    gameName: gameName,
                    character: character,
                    variant: variant,
                    characterZh: characterZh,
                    variantZh: variantZh,
                    label: characterZh,
                    fullLabel: variant == "default" ? characterZh : "\(characterZh) · \(variantZh)",
                    light: "\(baseURL)\(lightPath)?v=\(revision)",
                    dark: "\(baseURL)\(darkPath)?v=\(revision)"
                ))
            }
        }
    }
    entries.sort { $0.fullLabel.localizedStandardCompare($1.fullLabel) == .orderedAscending }
    let catalog = Catalog(version: 1, source: "smb", generated: generated, count: entries.count, entries: entries)
    return CatalogBuild(catalog: catalog, assets: assets)
}
