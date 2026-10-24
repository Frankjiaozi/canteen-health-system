// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "ZhiweiTray",
    platforms: [
        .iOS(.v17),
    ],
    products: [
        .library(
            name: "ZhiweiTray",
            targets: ["ZhiweiTray"]
        ),
    ],
    dependencies: [
        .package(path: "TrayCore"),
    ],
    targets: [
        .target(
            name: "ZhiweiTray",
            dependencies: [
                .product(name: "TrayCore", package: "TrayCore"),
            ],
            path: ".",
            exclude: ["TrayCore"],
            sources: ["ZhiweiTray/Sources"],
            resources: [
                .process("ZhiweiTray/Resources"),
            ]
        ),
    ]
)
