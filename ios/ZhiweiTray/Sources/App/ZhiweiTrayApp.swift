import SwiftUI
import TrayCore

@main
struct ZhiweiTrayApp: App {
    @StateObject private var store = TrayStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .environment(\.locale, Locale(identifier: "zh_Hans_CN"))
                .preferredColorScheme(.light)
                .tint(Theme.primary)
        }
    }
}
