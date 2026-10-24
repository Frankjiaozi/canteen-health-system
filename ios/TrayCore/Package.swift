// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "TrayCore",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [
        .library(name: "TrayCore", targets: ["TrayCore"]),
    ],
    targets: [
        .target(
            name: "TrayCore",
            resources: [.process("Resources")]
        ),
        .testTarget(
            name: "TrayCoreTests",
            dependencies: ["TrayCore"]
        ),
    ]
)
