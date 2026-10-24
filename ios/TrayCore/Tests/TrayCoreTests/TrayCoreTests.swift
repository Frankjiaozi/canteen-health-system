import XCTest
@testable import TrayCore

final class TrayCoreTests: XCTestCase {
    private let repo = MenuRepository.bundled()
    private var calendar: Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "Asia/Shanghai")!
        return cal
    }
    private var monday: Date {
        calendar.date(from: DateComponents(year: 2026, month: 10, day: 26))!
    }

    func testMenuHasFullWeek() {
        let menus = repo.weekMenus(containing: monday, calendar: calendar)
        XCTAssertEqual(menus.count, 7)
        XCTAssertEqual(menus.first?.label, "周一")
        XCTAssertEqual(menus.last?.label, "周日")
        for menu in menus {
            XCTAssertEqual(menu.meals.count, 3)
            for meal in menu.meals {
                XCTAssertFalse(meal.dishIDs.isEmpty, "\(menu.label) \(meal.type) menu is empty")
            }
        }
    }

    func testEveryMenuDishExists() {
        for template in repo.data.week {
            for meal in template.meals {
                for id in meal.dishIDs {
                    XCTAssertNotNil(repo.dish(id), "missing dish \(id)")
                }
            }
        }
    }

    func testLunchComboCoversAllSlots() throws {
        let menu = repo.menu(for: monday, calendar: calendar)
        let pool = repo.menuPool(for: menu, meal: .lunch)
        let combo = try XCTUnwrap(ComboEngine.best(from: pool, meal: .lunch, profile: UserProfile()))
        XCTAssertEqual(combo.dishes.count, 4)
        XCTAssertEqual(Set(combo.dishes.map(\.category)), Set(MealType.lunch.slots))
        XCTAssertEqual(combo.nutrition.calories, combo.dishes.reduce(0) { $0 + $1.nutrition.calories }, accuracy: 0.01)
        XCTAssertGreaterThan(combo.price, 0)
    }

    func testAllergensAreNeverRecommended() {
        let menu = repo.menu(for: monday, calendar: calendar)
        let pool = repo.menuPool(for: menu, meal: .dinner)
        var profile = UserProfile()
        profile.allergens = ["鸡蛋", "大豆", "虾"]
        let combos = ComboEngine.suggestions(from: pool, meal: .dinner, profile: profile, limit: 10)
        XCTAssertFalse(combos.isEmpty)
        for combo in combos {
            for dish in combo.dishes {
                XCTAssertTrue(
                    Set(dish.allergens).isDisjoint(with: profile.allergens),
                    "\(dish.name) contains a blocked allergen"
                )
            }
        }
    }

    func testBreakfastHasThreeSlots() throws {
        let menu = repo.menu(for: monday, calendar: calendar)
        let pool = repo.menuPool(for: menu, meal: .breakfast)
        let combo = try XCTUnwrap(ComboEngine.best(from: pool, meal: .breakfast, profile: UserProfile()))
        XCTAssertEqual(Set(combo.dishes.map(\.category)), Set(MealType.breakfast.slots))
    }

    func testCutGoalStaysNearCalorieTarget() throws {
        let menu = repo.menu(for: monday, calendar: calendar)
        let pool = repo.menuPool(for: menu, meal: .lunch)
        var profile = UserProfile()
        profile.goal = .cut
        profile.calorieTarget = 1600
        let combo = try XCTUnwrap(ComboEngine.best(from: pool, meal: .lunch, profile: profile))
        let target = NutritionMath.targets(for: profile, meal: .lunch)
        let gap = abs(combo.nutrition.calories - target.calories) / target.calories
        XCTAssertLessThan(gap, 0.35, "cut combo should land within 35% of the lunch target")
    }

    func testSuggestionsAreDeterministicAndRotate() {
        let menu = repo.menu(for: monday, calendar: calendar)
        let pool = repo.menuPool(for: menu, meal: .lunch)
        let profile = UserProfile()
        let a = ComboEngine.suggestions(from: pool, meal: .lunch, profile: profile, seed: 0, limit: 4)
        let b = ComboEngine.suggestions(from: pool, meal: .lunch, profile: profile, seed: 0, limit: 4)
        XCTAssertEqual(a.map(\.id), b.map(\.id))
        let c = ComboEngine.suggestions(from: pool, meal: .lunch, profile: profile, seed: 1, limit: 4)
        XCTAssertNotEqual(a.first?.id, c.first?.id, "换一套 should produce a different first combo")
    }

    func testCashBudgetIsRespectedWhenPossible() throws {
        let pool = repo.pool(for: .lunch)
        var profile = UserProfile()
        profile.budgetPerMeal = 12
        let combo = try XCTUnwrap(ComboEngine.best(from: pool, meal: .lunch, profile: profile))
        XCTAssertLessThanOrEqual(combo.price, 18, "should not blow far past a 12 CNY budget")
    }

    func testAlternativesChangeOnlyOneSlot() throws {
        let menu = repo.menu(for: monday, calendar: calendar)
        let pool = repo.menuPool(for: menu, meal: .lunch)
        let combo = try XCTUnwrap(ComboEngine.best(from: pool, meal: .lunch, profile: UserProfile()))
        let alternatives = ComboEngine.alternatives(
            for: .protein, in: combo, pool: pool, meal: .lunch, profile: UserProfile()
        )
        XCTAssertFalse(alternatives.isEmpty)
        XCTAssertFalse(alternatives.contains { $0.id == combo.dish(for: .protein)?.id })
    }

    func testHealthScoreBounds() {
        let profile = UserProfile()
        let target = NutritionMath.targets(for: profile, meal: .lunch)
        let perfect = Nutrition(
            calories: target.calories,
            protein: target.protein,
            fat: target.fat,
            carbs: target.carbs,
            fiber: target.fiber,
            sodium: target.sodium * 0.5
        )
        let score = NutritionMath.healthScore(for: perfect, target: target)
        XCTAssertGreaterThanOrEqual(score, 80)
        XCTAssertLessThanOrEqual(score, 100)
        let empty = NutritionMath.healthScore(for: .zero, target: target)
        XCTAssertLessThan(empty, 40)
    }

    func testJSONRoundTrip() throws {
        let menu = repo.menu(for: monday, calendar: calendar)
        let encoded = try JSONEncoder().encode(menu.meals)
        let decoded = try JSONDecoder().decode([Meal].self, from: encoded)
        XCTAssertEqual(decoded, menu.meals)
    }
}
