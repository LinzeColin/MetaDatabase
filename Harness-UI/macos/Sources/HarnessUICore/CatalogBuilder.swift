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

private func metaLabels(_ file: URL) -> Label? {
    guard let data = try? Data(contentsOf: file),
          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let character = object["characterZh"] as? String,
          let variant = object["variantZh"] as? String else { return nil }
    return Label(characterZh: character, variantZh: variant)
}

public func buildCatalog(
    sourceRoot: URL,
    baseURL: String = "http://127.0.0.1:3099",
    labels: [String: Label] = [:],
    now: Date = Date(),
    fileManager: FileManager = .default
) -> CatalogBuild {
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
                    light: "\(baseURL)\(lightPath)",
                    dark: "\(baseURL)\(darkPath)"
                ))
            }
        }
    }
    entries.sort { $0.fullLabel.localizedStandardCompare($1.fullLabel) == .orderedAscending }
    let formatter = ISO8601DateFormatter()
    let catalog = Catalog(version: 1, source: "smb", generated: formatter.string(from: now), count: entries.count, entries: entries)
    return CatalogBuild(catalog: catalog, assets: assets)
}
