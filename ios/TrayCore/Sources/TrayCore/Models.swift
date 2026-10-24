import Foundation

// MARK: - Nutrition

public struct Nutrition: Codable, Hashable, Sendable {
    public var calories: Double
    public var protein: Double
    public var fat: Double
    public var carbs: Double
    public var fiber: Double
    public var sodium: Double

    public init(
        calories: Double,
        protein: Double,
        fat: Double,
        carbs: Double,
        fiber: Double,
        sodium: Double
    ) {
        self.calories = calories
        self.protein = protein
        self.fat = fat
        self.carbs = carbs
        self.fiber = fiber
        self.sodium = sodium
    }

    public static let zero = Nutrition(calories: 0, protein: 0, fat: 0, carbs: 0, fiber: 0, sodium: 0)

    public static func + (lhs: Nutrition, rhs: Nutrition) -> Nutrition {
        Nutrition(
            calories: lhs.calories + rhs.calories,
            protein: lhs.protein + rhs.protein,
            fat: lhs.fat + rhs.fat,
            carbs: lhs.carbs + rhs.carbs,
            fiber: lhs.fiber + rhs.fiber,
            sodium: lhs.sodium + rhs.sodium
        )
    }

    public static func * (lhs: Nutrition, rhs: Double) -> Nutrition {
        Nutrition(
            calories: lhs.calories * rhs,
            protein: lhs.protein * rhs,
            fat: lhs.fat * rhs,
            carbs: lhs.carbs * rhs,
            fiber: lhs.fiber * rhs,
            sodium: lhs.sodium * rhs
        )
    }

    public func rounded() -> Nutrition {
        Nutrition(
            calories: calories.rounded(),
            protein: (protein * 10).rounded() / 10,
            fat: (fat * 10).rounded() / 10,
            carbs: (carbs * 10).rounded() / 10,
            fiber: (fiber * 10).rounded() / 10,
            sodium: sodium.rounded()
        )
    }

    /// Share of energy coming from protein / fat / carbohydrate.
    public var energySplit: (protein: Double, fat: Double, carbs: Double) {
        let p = protein * 4
        let f = fat * 9
        let c = carbs * 4
        let total = max(p + f + c, 1)
        return (p / total, f / total, c / total)
    }
}

// MARK: - Dish

public enum DishCategory: String, Codable, CaseIterable, Sendable {
    case staple
    case protein
    case vegetable
    case soup

    public var title: String {
        switch self {
        case .staple: return "主食"
        case .protein: return "荤菜"
        case .vegetable: return "素菜"
        case .soup: return "汤品"
        }
    }

    public var symbol: String {
        switch self {
        case .staple: return "takeoutbag.and.cup.and.straw"
        case .protein: return "flame"
        case .vegetable: return "leaf"
        case .soup: return "drop"
        }
    }
}

public struct Dish: Codable, Hashable, Identifiable, Sendable {
    public var id: String
    public var name: String
    public var category: DishCategory
    public var price: Double
    public var stall: String
    public var image: String
    public var nutrition: Nutrition
    public var allergens: [String]
    public var tags: [String]
    public var ingredients: [String]
    public var vegetarian: Bool
    public var spicy: Int
    public var popularity: Int
    public var note: String

    public init(
        id: String,
        name: String,
        category: DishCategory,
        price: Double,
        stall: String,
        image: String,
        nutrition: Nutrition,
        allergens: [String] = [],
        tags: [String] = [],
        ingredients: [String] = [],
        vegetarian: Bool = false,
        spicy: Int = 0,
        popularity: Int = 0,
        note: String = ""
    ) {
        self.id = id
        self.name = name
        self.category = category
        self.price = price
        self.stall = stall
        self.image = image
        self.nutrition = nutrition
        self.allergens = allergens
        self.tags = tags
        self.ingredients = ingredients
        self.vegetarian = vegetarian
        self.spicy = spicy
        self.popularity = popularity
        self.note = note
    }

    public var proteinDensity: Double {
        nutrition.calories > 0 ? nutrition.protein / nutrition.calories * 100 : 0
    }
}

// MARK: - Menu

public enum MealType: String, Codable, CaseIterable, Identifiable, Sendable {
    case breakfast
    case lunch
    case dinner

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .breakfast: return "早餐"
        case .lunch: return "午餐"
        case .dinner: return "晚餐"
        }
    }

    public var shortTitle: String {
        switch self {
        case .breakfast: return "早"
        case .lunch: return "午"
        case .dinner: return "晚"
        }
    }

    public var energyShare: Double {
        switch self {
        case .breakfast: return 0.30
        case .lunch: return 0.40
        case .dinner: return 0.30
        }
    }

    public var slots: [DishCategory] {
        switch self {
        case .breakfast: return [.staple, .protein, .vegetable]
        case .lunch, .dinner: return [.staple, .protein, .vegetable, .soup]
        }
    }

    public var defaultTime: String {
        switch self {
        case .breakfast: return "07:00 – 09:00"
        case .lunch: return "11:30 – 13:00"
        case .dinner: return "17:30 – 19:00"
        }
    }
}

public struct Meal: Codable, Hashable, Identifiable, Sendable {
    public var type: MealType
    public var time: String
    public var dishIDs: [String]

    public var id: String { type.rawValue }

    public init(type: MealType, time: String, dishIDs: [String]) {
        self.type = type
        self.time = time
        self.dishIDs = dishIDs
    }
}

public struct MenuDay: Identifiable, Hashable, Sendable {
    public var date: Date
    public var label: String
    public var meals: [Meal]

    public var id: Date { date }

    public init(date: Date, label: String, meals: [Meal]) {
        self.date = date
        self.label = label
        self.meals = meals
    }

    public func meal(_ type: MealType) -> Meal? {
        meals.first { $0.type == type }
    }
}

// MARK: - Data file

public struct CanteenInfo: Codable, Hashable, Sendable {
    public var name: String
    public var school: String
    public var updated: String
}

public struct TransparencyMeta: Codable, Hashable, Sendable {
    public var note: String
    public var oilPerPerson: Double
    public var saltPerPerson: Double
    public var traceBatches: Int
}

public struct DayTemplate: Codable, Hashable, Sendable {
    public var weekday: Int
    public var label: String
    public var meals: [Meal]
}

public struct MenuData: Codable, Sendable {
    public var canteen: CanteenInfo
    public var dishes: [String: Dish]
    public var week: [DayTemplate]
    public var meta: TransparencyMeta
}

// MARK: - Profile

public enum Goal: String, Codable, CaseIterable, Identifiable, Sendable {
    case balanced
    case cut
    case bulk

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .balanced: return "均衡"
        case .cut: return "减脂"
        case .bulk: return "增肌"
        }
    }

    public var subtitle: String {
        switch self {
        case .balanced: return "吃够种类，能量平稳"
        case .cut: return "控能量，优先蛋白质和蔬菜"
        case .bulk: return "补足蛋白，训练后恢复"
        }
    }

    public var symbol: String {
        switch self {
        case .balanced: return "circle.hexagongrid"
        case .cut: return "arrow.down.right"
        case .bulk: return "arrow.up.right"
        }
    }

    public var proteinRatio: Double {
        switch self {
        case .balanced: return 0.18
        case .cut: return 0.25
        case .bulk: return 0.22
        }
    }
}

public enum Allergen {
    public static let all = ["鸡蛋", "牛奶", "花生", "大豆", "虾", "小麦", "鱼类"]
}

public struct UserProfile: Codable, Equatable, Sendable {
    public var name: String
    public var goal: Goal
    public var calorieTarget: Double
    public var budgetPerMeal: Double
    public var allergens: Set<String>
    public var favorites: Set<String>

    public init(
        name: String = "同学",
        goal: Goal = .balanced,
        calorieTarget: Double = 2000,
        budgetPerMeal: Double = 15,
        allergens: Set<String> = [],
        favorites: Set<String> = []
    ) {
        self.name = name
        self.goal = goal
        self.calorieTarget = calorieTarget
        self.budgetPerMeal = budgetPerMeal
        self.allergens = allergens
        self.favorites = favorites
    }

    public var allergenList: [String] {
        Array(allergens).sorted()
    }
}

// MARK: - Targets

public struct NutritionTargets: Equatable, Sendable {
    public var calories: Double
    public var protein: Double
    public var fat: Double
    public var carbs: Double
    public var fiber: Double
    public var sodium: Double

    public init(
        calories: Double,
        protein: Double,
        fat: Double,
        carbs: Double,
        fiber: Double,
        sodium: Double
    ) {
        self.calories = calories
        self.protein = protein
        self.fat = fat
        self.carbs = carbs
        self.fiber = fiber
        self.sodium = sodium
    }
}

public enum NutritionMath {
    public static func dailyTargets(for profile: UserProfile) -> NutritionTargets {
        let calories = max(profile.calorieTarget, 1200)
        let protein = calories * profile.goal.proteinRatio / 4
        let fat = calories * 0.27 / 9
        let carbs = calories * (1 - profile.goal.proteinRatio - 0.27) / 4
        let fiber = min(max(calories / 1000 * 12, 20), 35)
        let sodium = 2000.0
        return NutritionTargets(
            calories: calories,
            protein: protein,
            fat: fat,
            carbs: carbs,
            fiber: fiber,
            sodium: sodium
        )
    }

    public static func targets(for profile: UserProfile, meal: MealType) -> NutritionTargets {
        let day = dailyTargets(for: profile)
        return NutritionTargets(
            calories: day.calories * meal.energyShare,
            protein: day.protein * meal.energyShare,
            fat: day.fat * meal.energyShare,
            carbs: day.carbs * meal.energyShare,
            fiber: day.fiber * meal.energyShare,
            sodium: day.sodium * meal.energyShare
        )
    }

    /// 0...100, higher is better. Penalises allergen-free imbalances gently.
    public static func healthScore(for nutrition: Nutrition, target: NutritionTargets) -> Int {
        let calorieFit = max(0, 1 - abs(nutrition.calories - target.calories) / max(target.calories, 1))
        let proteinFit = min(nutrition.protein / max(target.protein, 1), 1.25)
        let fiberFit = min(nutrition.fiber / max(target.fiber, 1), 1.2)
        let sodiumFit = max(0, 1 - max(0, nutrition.sodium - target.sodium) / max(target.sodium * 0.8, 1))
        let score = calorieFit * 40 + proteinFit * 30 + fiberFit * 15 + sodiumFit * 15
        return Int(min(max(score.rounded(), 0), 100))
    }
}

// MARK: - Logging

public struct MealLogEntry: Codable, Hashable, Identifiable, Sendable {
    public var id: UUID
    public var date: Date
    public var meal: MealType
    public var dishIDs: [String]
    public var createdAt: Date

    public init(id: UUID = UUID(), date: Date, meal: MealType, dishIDs: [String], createdAt: Date = Date()) {
        self.id = id
        self.date = date
        self.meal = meal
        self.dishIDs = dishIDs
        self.createdAt = createdAt
    }
}

public struct DaySummary: Equatable, Sendable {
    public var nutrition: Nutrition
    public var price: Double
    public var entries: Int

    public init(nutrition: Nutrition, price: Double, entries: Int) {
        self.nutrition = nutrition
        self.price = price
        self.entries = entries
    }

    public static let empty = DaySummary(nutrition: .zero, price: 0, entries: 0)
}
