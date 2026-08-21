import Foundation

public let harnessGameSlugs: [String: String] = [
    "原神": "genshin",
    "崩铁": "hsr",
    "绝区零": "zzz",
    "鸣潮": "wuwa",
    "异环": "nte",
]

public struct CatalogEntry: Codable, Equatable, Sendable {
    public let id: String
    public let game: String
    public let gameName: String
    public let character: String
    public let variant: String
    public let characterZh: String
    public let variantZh: String
    public let label: String
    public let fullLabel: String
    public let light: String
    public let dark: String
}

public struct Catalog: Codable, Equatable, Sendable {
    public let version: Int
    public let source: String
    public let generated: String
    public let count: Int
    public let entries: [CatalogEntry]

    public static let empty = Catalog(version: 1, source: "smb", generated: "", count: 0, entries: [])
}

public struct Label: Codable, Equatable, Sendable {
    public let characterZh: String
    public let variantZh: String
}

public struct HarnessState: Codable, Equatable, Sendable {
    public var version: Int = 1
    public var mode: String = "gallery"
    public var selected: String?
    public var intervalMs: Int = 14_400_000
    public var hidden: [String] = []
    public var cycle: [String] = []
    public var cursor: Int = 0
    public var lastRotate: Int64 = 0
    public var updated: Int64 = 0

    public init() {}
}

public struct HarnessConfiguration: Codable, Equatable, Sendable {
    public var version: Int = 1
    public var port: UInt16 = 3099
    public var smbURL = "smb://192.168.0.1/share/03_资料库/MetaData/HarnessUI/"
    public var sourcePath = ""

    public init() {}
}

public struct CatalogBuild: Sendable {
    public let catalog: Catalog
    public let assets: [String: URL]
}
