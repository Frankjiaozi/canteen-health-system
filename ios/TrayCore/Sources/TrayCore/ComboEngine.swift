import Foundation

public struct Combo: Identifiable, Hashable, Sendable {
    public let id: String
    public let meal: MealType
    public let dishes: [Dish]
    public let nutrition: Nutrition
    public let price: Double
    public let score: Double
    public let reasons: [String]

    public init(
        meal: MealType,
        dishes: [Dish],
        score: Double,
        reasons: [String]
    ) {
        self.id = dishes.map(\.id).joined(separator: "+")
        self.meal = meal
        self.dishes = dishes
        self.nutrition = dishes.reduce(.zero) { $0 + $1.nutrition }
        self.price = dishes.reduce(0) { $0 + $1.price }
        self.score = score
        self.reasons = reasons
    }

    public func dish(for category: DishCategory) -> Dish? {
        dishes.first { $0.category == category }
    }

    public var healthScore: Int { Int(min(max(score.rounded(), 0), 100)) }
}

public enum ComboEngine {
    /// Returns up to `limit` distinct combos, best first. `seed` rotates the top results so
    /// "换一套" produces a genuinely different suggestion without becoming random noise.
    public static func suggestions(
        from pool: [Dish],
        meal: MealType,
        profile: UserProfile,
        seed: Int = 0,
        limit: Int = 5
    ) -> [Combo] {
        let available = pool.filter { dish in
            Set(dish.allergens).isDisjoint(with: profile.allergens)
        }
        guard !available.isEmpty else { return [] }

        let target = NutritionMath.targets(for: profile, meal: meal)
        let grouped = Dictionary(grouping: available, by: \.category)
        let slots = meal.slots

        var combos: [Combo] = []

        func walk(_ slotIndex: Int, _ chosen: [Dish]) {
            if slotIndex == slots.count {
                combos.append(makeCombo(chosen, meal: meal, profile: profile, target: target))
                return
            }
            let category = slots[slotIndex]
            let options = grouped[category] ?? []
            if options.isEmpty {
                // Soup is optional; everything else is required.
                if category == .soup { walk(slotIndex + 1, chosen) }
                return
            }
            for dish in options {
                walk(slotIndex + 1, chosen + [dish])
            }
        }

        walk(0, [])
        guard !combos.isEmpty else { return [] }

        // Budget is a hard constraint whenever at least one combo fits: a recommendation
        // that breaks the student's budget is not a recommendation.
        let affordable = combos.filter { $0.price <= profile.budgetPerMeal }
        var ranked = affordable.isEmpty ? combos : affordable
        ranked.sort {
            if abs($0.score - $1.score) > 0.001 { return $0.score > $1.score }
            return $0.id < $1.id
        }

        var seen = Set<String>()
        var unique: [Combo] = []
        for combo in ranked where !seen.contains(combo.id) {
            seen.insert(combo.id)
            unique.append(combo)
        }

        guard seed != 0, unique.count > 1 else { return Array(unique.prefix(limit)) }
        let window = Array(unique.prefix(max(limit * 2, limit)))
        let shift = abs(seed) % window.count
        let rotated = Array(window[shift...]) + Array(window[..<shift])
        return Array(rotated.prefix(limit))
    }

    public static func best(
        from pool: [Dish],
        meal: MealType,
        profile: UserProfile
    ) -> Combo? {
        suggestions(from: pool, meal: meal, profile: profile, limit: 1).first
    }

    /// Alternatives for one slot inside an existing combo, ranked by how well they keep
    /// the tray on target.
    public static func alternatives(
        for category: DishCategory,
        in combo: Combo,
        pool: [Dish],
        meal: MealType,
        profile: UserProfile
    ) -> [Dish] {
        let target = NutritionMath.targets(for: profile, meal: meal)
        let anchor = combo.dishes.filter { $0.category != category }
        let currentID = combo.dish(for: category)?.id
        return pool
            .filter { $0.category == category }
            .filter { Set($0.allergens).isDisjoint(with: profile.allergens) }
            .filter { $0.id != currentID }
            .filter { candidate in !anchor.contains(where: { $0.id == candidate.id }) }
            .map { candidate -> (Dish, Double) in
                let trial = Combo(meal: meal, dishes: anchor + [candidate], score: 0, reasons: [])
                let score = quality(trial.nutrition, price: trial.price, dishes: trial.dishes, profile: profile, target: target)
                return (candidate, score)
            }
            .sorted { $0.1 > $1.1 }
            .map(\.0)
    }

    // MARK: - Scoring

    private static func makeCombo(
        _ dishes: [Dish],
        meal: MealType,
        profile: UserProfile,
        target: NutritionTargets
    ) -> Combo {
        let nutrition = dishes.reduce(Nutrition.zero) { $0 + $1.nutrition }
        let price = dishes.reduce(0) { $0 + $1.price }
        let score = quality(nutrition, price: price, dishes: dishes, profile: profile, target: target)
        return Combo(meal: meal, dishes: dishes, score: score, reasons: reasons(
            nutrition: nutrition, price: price, dishes: dishes, profile: profile, target: target
        ))
    }

    private static func quality(
        _ nutrition: Nutrition,
        price: Double,
        dishes: [Dish],
        profile: UserProfile,
        target: NutritionTargets
    ) -> Double {
        let calorieGap = abs(nutrition.calories - target.calories) / max(target.calories, 1)
        let calorieScore = max(0, 1 - calorieGap) * 42
        let overPenalty = max(0, calorieGap - 0.30) * 70

        let proteinScore = min(nutrition.protein / max(target.protein, 1), 1.25) * 24
        let fiberScore = min(nutrition.fiber / max(target.fiber, 1), 1.2) * 10
        let vegCount = dishes.filter { $0.category == .vegetable }.count
        let vegScore = min(Double(vegCount), 2) * 4
        let sodiumPenalty = max(0, nutrition.sodium - target.sodium) / max(target.sodium, 1) * 10

        let budgetScore: Double
        if price <= profile.budgetPerMeal {
            budgetScore = 8
        } else {
            budgetScore = -min(30, (price - profile.budgetPerMeal) / max(profile.budgetPerMeal, 1) * 40)
        }

        let popularity = dishes.map { Double($0.popularity) }.reduce(0, +) / Double(max(dishes.count, 1)) / 20
        let vegetarianBonus = dishes.filter(\.vegetarian).count == dishes.count ? 2.0 : 0.0

        var total = calorieScore
        total += proteinScore
        total += fiberScore
        total += vegScore
        total += budgetScore
        total += popularity
        total += vegetarianBonus
        total -= sodiumPenalty
        total -= overPenalty
        return max(0, min(100, total))
    }

    private static func reasons(
        nutrition: Nutrition,
        price: Double,
        dishes: [Dish],
        profile: UserProfile,
        target: NutritionTargets
    ) -> [String] {
        var result: [String] = []
        let proteinCoverage = nutrition.protein / max(target.protein, 1)
        if proteinCoverage >= 0.9 {
            result.append("蛋白质 \(Int(nutrition.protein.rounded()))g，达到本餐目标")
        } else {
            result.append("蛋白质 \(Int(nutrition.protein.rounded()))g，还可再加一份蛋/奶")
        }
        if price <= profile.budgetPerMeal {
            result.append("合计 ¥\(String(format: "%.1f", price))，在预算内")
        } else {
            result.append("合计 ¥\(String(format: "%.1f", price))，超出预算 ¥\(String(format: "%.1f", price - profile.budgetPerMeal))")
        }
        if nutrition.sodium <= target.sodium {
            result.append("钠 \(Int(nutrition.sodium.rounded()))mg，清淡不口渴")
        }
        let vegCount = dishes.filter { $0.category == .vegetable }.count
        result.append("\(vegCount) 份蔬菜 · \(Int(nutrition.fiber.rounded()))g 膳食纤维")
        return result
    }
}
