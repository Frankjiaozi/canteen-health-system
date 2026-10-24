import Foundation

public struct MenuRepository {
    public let data: MenuData
    private let sortedDishes: [Dish]

    public init(data: MenuData) {
        self.data = data
        self.sortedDishes = data.dishes.values.sorted { $0.popularity > $1.popularity }
    }

    public static func bundled() -> MenuRepository {
        guard
            let url = Bundle.module.url(forResource: "menu", withExtension: "json"),
            let raw = try? Data(contentsOf: url),
            let decoded = try? JSONDecoder().decode(MenuData.self, from: raw)
        else {
            fatalError("TrayCore: bundled menu.json is missing or malformed")
        }
        return MenuRepository(data: decoded)
    }

    public var canteen: CanteenInfo { data.canteen }
    public var meta: TransparencyMeta { data.meta }
    public var allDishes: [Dish] { sortedDishes }

    public func dish(_ id: String) -> Dish? { data.dishes[id] }

    public func dishes(_ ids: [String]) -> [Dish] {
        ids.compactMap { data.dishes[$0] }
    }

    /// ISO weekday: Monday = 1 … Sunday = 7.
    public static func isoWeekday(for date: Date, calendar: Calendar = .current) -> Int {
        let weekday = calendar.component(.weekday, from: date)
        return (weekday + 5) % 7 + 1
    }

    public func menu(for date: Date, calendar: Calendar = .current) -> MenuDay {
        let iso = Self.isoWeekday(for: date, calendar: calendar)
        let template = data.week.first { $0.weekday == iso } ?? data.week[0]
        return MenuDay(date: calendar.startOfDay(for: date), label: template.label, meals: template.meals)
    }

    public func weekMenus(containing date: Date, calendar: Calendar = .current) -> [MenuDay] {
        let weekday = Self.isoWeekday(for: date, calendar: calendar)
        let start = calendar.date(byAdding: .day, value: -(weekday - 1), to: calendar.startOfDay(for: date)) ?? date
        return (0..<7).compactMap { offset in
            guard let day = calendar.date(byAdding: .day, value: offset, to: start) else { return nil }
            return menu(for: day, calendar: calendar)
        }
    }

    /// Every dish that appears at least once for the given meal in the weekly rotation.
    public func pool(for meal: MealType) -> [Dish] {
        var seen = Set<String>()
        var result: [Dish] = []
        for template in data.week {
            guard let entry = template.meals.first(where: { $0.type == meal }) else { continue }
            for id in entry.dishIDs where !seen.contains(id) {
                seen.insert(id)
                if let dish = data.dishes[id] { result.append(dish) }
            }
        }
        return result.sorted { $0.popularity > $1.popularity }
    }

    public func menuPool(for day: MenuDay, meal: MealType) -> [Dish] {
        guard let entry = day.meal(meal) else { return [] }
        return dishes(entry.dishIDs)
    }
}
