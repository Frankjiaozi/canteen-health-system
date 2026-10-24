# 知味 · 餐盘 (Zhiwei Tray)

面向高校学生的「食堂官方菜单 → 一餐决策」iOS 应用。把食堂后厨已有的菜品、配方、营养与过敏原数据，变成学生看得懂、用得上的一餐建议。

- **离线优先**：菜单与营养数据随包内置，记录只写本机，不登录、不联网。
- **按目标搭配**：均衡 / 减脂 / 增肌三套目标，结合预算、过敏原，实时生成「主食 + 荤菜 + 素菜 + 汤」组合。
- **营养透明**：每道菜的标准份量热量、蛋白质、脂肪、碳水、纤维、钠，以及人均用油用盐与食材溯源。
- **可解释推荐**：每套搭配给出蛋白质达成、预算、钠与蔬菜份数的理由。

## 目录

```
ios/
  TrayCore/                 # 纯 Swift 逻辑包（模型、推荐算法、测试）
  ZhiweiTray/               # SwiftUI 应用（XcodeGen 工程描述）
  Package.swift             # xtool / SwiftPM 入口
  xtool.yml                 # xtool bundle ID
.github/workflows/ios-build.yml  # macOS CI：测试、截图、未签名 IPA
```

## 构建

### 方式一：xtool（WSL / Linux，需 Xcode.xip）

xtool 需要 Apple 的 iOS SDK，按官方文档准备 Swift 6.4 与 `Xcode.xip` 后：

```bash
cd ios
xtool auth login
xtool sdk install /path/to/Xcode.xip --slim
xtool build          # 产出未签名 .ipa
```

### 方式二：Xcode / macOS（本仓库 CI 使用）

```bash
cd ios/TrayCore && swift test
cd ../ZhiweiTray
brew install xcodegen
xcodegen generate
xcodebuild -project ZhiweiTray.xcodeproj -scheme ZhiweiTray \
  -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16 Pro' build
```

未签名真机 IPA：

```bash
xcodebuild -project ZhiweiTray.xcodeproj -scheme ZhiweiTray -configuration Release \
  -sdk iphoneos CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO build
# 将 .app 放入 Payload/ 后 zip 成 .ipa
```

## 数据说明

`ios/TrayCore/Sources/TrayCore/Resources/menu.json` 为演示数据：菜品名称、图片与营养结构来自「知味 · 校园智慧膳食平台」的示例菜品，营养值按标准份量估算，用于产品体验；正式版应由食堂配方核算后通过接口下发。

## 许可

仅用于演示与评审。
