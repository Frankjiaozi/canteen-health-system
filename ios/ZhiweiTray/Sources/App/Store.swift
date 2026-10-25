import Foundation
import SwiftUI
import TrayCore

enum AppTab: String, Hashable {
    case today
    case menu
    case tray
    case log
    case profile
}

/// Lets screenshot/demo builds pin "now" so every screen shows a coherent date and meal.
enum AppClock {
    static let fixedNow: Date? = {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: "-demo-now"), args.indices.contains(index + 1) else {
            return nil
        }
        return ISO8601DateFormatter().date(from: args[index + 1])
    }()

    static var now: Date { fixedNow ?? Date() }
}

@MainActor
final class TrayStore: ObservableObject {
    @Published var profile: UserProfile
    @Published var logs: [MealLogEntry]
    @Published var tray: [Dish] = []
    @Published var trayMeal: MealType = .lunch
    @Published var selectedDate: Date = AppClock.now
    @Published var selectedMeal: MealType = .lunch
    @Published var suggestionSeed: Int = 0
    @Published var selectedTab: AppTab
    @Published var toast: String?

    let repository: MenuRepository

    private struct PersistedState: Codable {
        var profile: UserProfile
        var logs: [MealLogEntry]
    }

    init(repository: MenuRepository = .bundled()) {
        self.repository = repository
        self.selectedTab = TrayStore.initialTab()
        self.profile = UserProfile()
        self.logs = []

        if let data = try? Data(contentsOf: Self.storageURL),
           let state = try? JSONDecoder().decode(PersistedState.self, from: data) {
            self.profile = state.profile
            self.logs = state.logs
        } else {
            self.logs = Self.demoLogs(repository: repository)
            save()
        }

        self.selectedMeal = Self.mealForNow()

        if ProcessInfo.processInfo.arguments.contains("-demo-tray"),
           let combo = ComboEngine.best(
               from: repository.menuPool(for: menu(for: AppClock.now), meal: .lunch),
               meal: .lunch,
               profile: profile
           ) {
            self.tray = combo.dishes
            self.trayMeal = .lunch
        }
    }

    // MARK: - Persistence

    private static var directoryURL: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("ZhiweiTray", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private static var storageURL: URL {
        directoryURL.appendingPathComponent("state.json")
    }

    func save() {
        let state = PersistedState(profile: profile, logs: logs)
        guard let data = try? JSONEncoder().encode(state) else { return }
        try? data.write(to: Self.storageURL, options: [.atomic])
    }

    // MARK: - Menu

    func menu(for date: Date) -> MenuDay {
        repository.menu(for: date)
    }

    var todayMenu: MenuDay { menu(for: AppClock.now) }

    func pool(for meal: MealType) -> [Dish] {
        repository.pool(for: meal)
    }

    func todayPool(for meal: MealType) -> [Dish] {
        repository.menuPool(for: todayMenu, meal: meal)
    }

    // MARK: - Recommendations

    func recommendations(for meal: MealType, limit: Int = 4) -> [Combo] {
        ComboEngine.suggestions(
            from: todayPool(for: meal),
            meal: meal,
            profile: profile,
            seed: suggestionSeed,
            limit: limit
        )
    }

    func bestCombo(for meal: MealType) -> Combo? {
        ComboEngine.best(from: todayPool(for: meal), meal: meal, profile: profile)
    }

    func shuffleSuggestions() {
        suggestionSeed += 1
    }

    // MARK: - Tray

    func addToTray(_ dish: Dish, meal: MealType? = nil) {
        if let meal { trayMeal = meal }
        if let index = tray.firstIndex(where: { $0.category == dish.category }) {
            tray[index] = dish
        } else {
            tray.append(dish)
        }
        sortTray()
    }

    func removeFromTray(_ dish: Dish) {
        tray.removeAll { $0.id == dish.id }
    }

    func clearTray() {
        tray.removeAll()
    }

    func apply(_ combo: Combo) {
        trayMeal = combo.meal
        tray = combo.dishes
        sortTray()
    }

    private func sortTray() {
        let order = trayMeal.slots
        tray.sort { lhs, rhs in
            let l = order.firstIndex(of: lhs.category) ?? 99
            let r = order.firstIndex(of: rhs.category) ?? 99
            return l < r
        }
    }

    var trayNutrition: Nutrition {
        tray.reduce(.zero) { $0 + $1.nutrition }
    }

    var trayPrice: Double {
        tray.reduce(0) { $0 + $1.price }
    }

    var trayHealthScore: Int {
        NutritionMath.healthScore(
            for: trayNutrition,
            target: NutritionMath.targets(for: profile, meal: trayMeal)
        )
    }

    func saveTray() -> Bool {
        guard !tray.isEmpty else { return false }
        let entry = MealLogEntry(date: Calendar.current.startOfDay(for: AppClock.now), meal: trayMeal, dishIDs: tray.map(\.id))
        logs.removeAll { Calendar.current.isDate($0.date, inSameDayAs: entry.date) && $0.meal == entry.meal }
        logs.append(entry)
        logs.sort { $0.date > $1.date }
        tray.removeAll()
        save()
        toast = "已记入\(trayMeal.title)"
        return true
    }

    // MARK: - Logs

    func log(meal: MealType, dishIDs: [String], date: Date = AppClock.now) {
        let entry = MealLogEntry(date: Calendar.current.startOfDay(for: date), meal: meal, dishIDs: dishIDs)
        logs.removeAll { Calendar.current.isDate($0.date, inSameDayAs: entry.date) && $0.meal == meal }
        logs.append(entry)
        logs.sort { $0.date > $1.date }
        save()
        toast = "已记录\(meal.title)"
    }

    func delete(_ entry: MealLogEntry) {
        logs.removeAll { $0.id == entry.id }
        save()
    }

    func entries(for date: Date) -> [MealLogEntry] {
        logs.filter { Calendar.current.isDate($0.date, inSameDayAs: date) }
            .sorted { $0.meal.sortIndex < $1.meal.sortIndex }
    }

    func summary(for date: Date) -> DaySummary {
        let entries = entries(for: date)
        let ids = entries.flatMap(\.dishIDs)
        let dishes = repository.dishes(ids)
        return DaySummary(
            nutrition: dishes.reduce(.zero) { $0 + $1.nutrition },
            price: dishes.reduce(0) { $0 + $1.price },
            entries: entries.count
        )
    }

    func dishes(for entry: MealLogEntry) -> [Dish] {
        repository.dishes(entry.dishIDs)
    }

    func lastSevenDays(endingAt date: Date = AppClock.now) -> [(date: Date, summary: DaySummary)] {
        let calendar = Calendar.current
        let end = calendar.startOfDay(for: date)
        return (0..<7).reversed().compactMap { offset in
            guard let day = calendar.date(byAdding: .day, value: -offset, to: end) else { return nil }
            return (day, summary(for: day))
        }
    }

    func proteinDaysMet(endingAt date: Date = AppClock.now) -> Int {
        let target = NutritionMath.dailyTargets(for: profile).protein * 0.85
        return lastSevenDays(endingAt: date).filter { $0.summary.nutrition.protein >= target }.count
    }

    // MARK: - Favorites

    func isFavorite(_ dish: Dish) -> Bool {
        profile.favorites.contains(dish.id)
    }

    func toggleFavorite(_ dish: Dish) {
        if profile.favorites.contains(dish.id) {
            profile.favorites.remove(dish.id)
        } else {
            profile.favorites.insert(dish.id)
        }
        save()
    }

    // MARK: - Demo helpers

    func resetDemo() {
        profile = UserProfile()
        logs = Self.demoLogs(repository: repository)
        tray.removeAll()
        suggestionSeed = 0
        save()
        toast = "演示数据已重置"
    }

    static func mealForNow(now: Date = AppClock.now) -> MealType {
        let hour = Calendar.current.component(.hour, from: now)
        if hour < 10 { return .breakfast }
        if hour < 15 { return .lunch }
        return .dinner
    }

    private static func initialTab() -> AppTab {
        let args = ProcessInfo.processInfo.arguments
        for tab in [AppTab.menu, .tray, .log, .profile, .today] {
            if args.contains("-screen-\(tab.rawValue)") || args.contains("-screen") {
                return tab
            }
        }
        return .today
    }

    private static func demoLogs(repository: MenuRepository) -> [MealLogEntry] {
        var result: [MealLogEntry] = []
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: AppClock.now)
        for offset in 1...4 {
            guard let day = calendar.date(byAdding: .day, value: -offset, to: today) else { continue }
            let menu = repository.menu(for: day)
            for meal in [MealType.breakfast, .lunch, .dinner] {
                if let combo = ComboEngine.best(
                    from: repository.menuPool(for: menu, meal: meal),
                    meal: meal,
                    profile: UserProfile()
                ) {
                    var ids = combo.dishes.map(\.id)
                    if meal == .breakfast, !ids.contains("hot_milk") {
                        ids.append("hot_milk")
                    }
                    result.append(MealLogEntry(date: day, meal: meal, dishIDs: ids))
                }
            }
        }
        if let breakfast = ComboEngine.best(
            from: repository.menuPool(for: repository.menu(for: today), meal: .breakfast),
            meal: .breakfast,
            profile: UserProfile()
        ) {
            var ids = breakfast.dishes.map(\.id)
            if !ids.contains("hot_milk") { ids.append("hot_milk") }
            result.append(MealLogEntry(date: today, meal: .breakfast, dishIDs: ids))
        }
        return result
    }
}

extension MealType {
    var sortIndex: Int {
        switch self {
        case .breakfast: return 0
        case .lunch: return 1
        case .dinner: return 2
        }
    }
}
