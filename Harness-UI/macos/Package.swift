// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "HarnessUI",
    platforms: [.macOS(.v12)],
    products: [
        .library(name: "HarnessUICore", targets: ["HarnessUICore"]),
        .executable(name: "HarnessUIApp", targets: ["HarnessUIApp"]),
    ],
    targets: [
        .target(name: "HarnessUICore"),
        .executableTarget(name: "HarnessUIApp", dependencies: ["HarnessUICore"]),
        .testTarget(name: "HarnessUICoreTests", dependencies: ["HarnessUICore"]),
    ]
)
