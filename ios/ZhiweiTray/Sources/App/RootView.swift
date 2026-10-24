import SwiftUI
import TrayCore

struct RootView: View {
    @EnvironmentObject private var store: TrayStore

    var body: some View {
        ZStack(alignment: .top) {
            TabView(selection: $store.selectedTab) {
                TodayView()
                    .tabItem { Label("今天", systemImage: "sun.max") }
                    .tag(AppTab.today)

                MenuView()
                    .tabItem { Label("菜单", systemImage: "square.grid.2x2") }
                    .tag(AppTab.menu)

                TrayView()
                    .tabItem { Label("餐盘", systemImage: "circle.hexagongrid") }
                    .tag(AppTab.tray)

                LogView()
                    .tabItem { Label("记录", systemImage: "chart.bar") }
                    .tag(AppTab.log)

                ProfileView()
                    .tabItem { Label("我的", systemImage: "person") }
                    .tag(AppTab.profile)
            }
            .toolbarBackground(Theme.card, for: .tabBar)
            .toolbarBackground(.visible, for: .tabBar)

            if let toast = store.toast {
                ToastView(text: toast)
                    .padding(.top, 8)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .zIndex(10)
            }
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: store.toast)
        .onChange(of: store.toast) { _, newValue in
            guard let newValue else { return }
            Task {
                try? await Task.sleep(nanoseconds: 1_900_000_000)
                if store.toast == newValue {
                    store.toast = nil
                }
            }
        }
    }
}
