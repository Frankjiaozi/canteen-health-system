import SwiftUI
import TrayCore

struct TodayView: View {
    @EnvironmentObject private var store: TrayStore
    @State private var detailDish: Dish?

    private var currentMeal: MealType { TrayStore.mealForNow() }

    var body: some View {
        NavigationStack {
            ScrollView(showsIndicators: false) {
                VStack(spacing: 18) {
                    header
                    nutritionCard
                    suggestionCard
                    mealsCard
                    transparencyCard
                }
                .padding(.horizontal, Theme.pagePadding)
                .padding(.top, 8)
                .padding(.bottom, 110)
            }
            .background(Theme.background.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .sheet(item: $detailDish) { dish in
                DishDetailView(dish: dish, meal: currentMeal)
                    .environmentObject(store)
            }
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 5) {
                Text(dateLine)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Theme.muted)
                    .textCase(.uppercase)
                    .tracking(0.6)
                Text("\(greeting)，\(store.profile.name)")
                    .font(.traySerif(29, weight: .bold))
                    .foregroundStyle(Theme.ink)
                HStack(spacing: 5) {
                    Circle().fill(Theme.sage).frame(width: 6, height: 6)
                    Text(store.repository.canteen.name)
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.muted)
                }
            }
            Spacer()
            ZStack {
                Circle()
                    .fill(Theme.primarySoft)
                    .frame(width: 46, height: 46)
                Text("味")
                    .font(.traySerif(22, weight: .bold))
                    .foregroundStyle(Theme.primary)
            }
        }
        .padding(.top, 6)
    }

    private var dateLine: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_Hans_CN")
        formatter.dateFormat = "M月d日 EEEE"
        return formatter.string(from: Date())
    }

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        switch hour {
        case 5..<11: return "早上好"
        case 11..<14: return "中午好"
        case 14..<18: return "下午好"
        default: return "晚上好"
        }
    }

    // MARK: - Nutrition

    private var nutritionCard: some View {
        let summary = store.summary(for: Date())
        let target = NutritionMath.dailyTargets(for: store.profile)
        return VStack(spacing: 16) {
            HStack {
                SectionHeader(title: "今日营养", subtitle: summary.entries > 0 ? "已记录 \(summary.entries) 餐" : "等待第一餐")
                Text("目标 \(Int(target.calories)) kcal")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.muted)
            }

            HStack(spacing: 20) {
                ZStack {
                    ProgressRing(progress: summary.nutrition.calories / max(target.calories, 1), lineWidth: 9)
                    VStack(spacing: 0) {
                        Text("\(Int(summary.nutrition.calories.rounded()))")
                            .font(.trayNumber(23))
                            .foregroundStyle(Theme.ink)
                        Text("kcal")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(Theme.muted)
                    }
                }
                .frame(width: 98, height: 98)

                VStack(spacing: 11) {
                    MacroBar(
                        title: "蛋白质", value: summary.nutrition.protein,
                        target: target.protein, unit: "g", tint: Theme.primary
                    )
                    MacroBar(
                        title: "脂肪", value: summary.nutrition.fat,
                        target: target.fat, unit: "g", tint: Theme.gold
                    )
                    MacroBar(
                        title: "碳水", value: summary.nutrition.carbs,
                        target: target.carbs, unit: "g", tint: Theme.accent
                    )
                }
            }
        }
        .trayCard()
    }

    // MARK: - Suggestion

    @ViewBuilder
    private var suggestionCard: some View {
        if let combo = store.recommendations(for: currentMeal, limit: 1).first {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    HStack(spacing: 6) {
                        Image(systemName: "sparkles")
                            .font(.system(size: 12, weight: .semibold))
                        Text("为你搭配")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundStyle(.white.opacity(0.82))
                    Spacer()
                    Text("\(currentMeal.title) · \(Int(combo.nutrition.calories.rounded())) kcal")
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.white.opacity(0.75))
                }

                HStack(spacing: 9) {
                    ForEach(combo.dishes.prefix(3)) { dish in
                        DishImageView(name: dish.image, symbol: dish.category.symbol)
                            .frame(width: 66, height: 66)
                            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 16, style: .continuous)
                                    .stroke(.white.opacity(0.26), lineWidth: 1)
                            )
                    }
                    Spacer(minLength: 0)
                }

                VStack(alignment: .leading, spacing: 5) {
                    Text(combo.dishes.map(\.name).joined(separator: " · "))
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                    Text("蛋白质 \(Int(combo.nutrition.protein.rounded()))g · 蔬菜 \(combo.dishes.filter { $0.category == .vegetable }.count) 份")
                        .font(.system(size: 12))
                        .foregroundStyle(.white.opacity(0.72))
                }

                HStack(spacing: 10) {
                    Button {
                        store.apply(combo)
                        store.selectedTab = .tray
                    } label: {
                        Text("就吃这套 · ¥\(String(format: "%.1f", combo.price))")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(Theme.primary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(.white, in: Capsule())
                    }
                    .buttonStyle(PressableButtonStyle())

                    Button {
                        withAnimation(.easeInOut(duration: 0.25)) {
                            store.shuffleSuggestions()
                        }
                    } label: {
                        Image(systemName: "arrow.triangle.2.circlepath")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(.white)
                            .frame(width: 44, height: 44)
                            .background(.white.opacity(0.14), in: Circle())
                    }
                    .buttonStyle(PressableButtonStyle())
                }
            }
            .padding(18)
            .background(
                LinearGradient(
                    colors: [Theme.primary, Color(hex: 0x173E33)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ),
                in: RoundedRectangle(cornerRadius: 24, style: .continuous)
            )
            .overlay(alignment: .topTrailing) {
                Circle()
                    .fill(Theme.accent.opacity(0.22))
                    .frame(width: 120, height: 120)
                    .blur(radius: 6)
                    .offset(x: 40, y: -60)
                    .allowsHitTesting(false)
            }
            .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
            .shadow(color: Theme.primary.opacity(0.22), radius: 18, y: 10)
        }
    }

    // MARK: - Meals

    private var mealsCard: some View {
        VStack(spacing: 0) {
            HStack {
                SectionHeader(title: "今日菜单", subtitle: "由食堂后厨同步")
                Button {
                    store.selectedTab = .menu
                } label: {
                    Text("全部")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Theme.primary)
                }
            }
            .padding(.bottom, 6)

            ForEach(Array(MealType.allCases.enumerated()), id: \.element.id) { index, meal in
                mealRow(meal)
                if index < MealType.allCases.count - 1 {
                    Divider().overlay(Theme.line).padding(.leading, 54)
                }
            }
        }
        .trayCard(padding: 16)
    }

    private func mealRow(_ meal: MealType) -> some View {
        let menu = store.menu(for: Date())
        let entry = menu.meal(meal)
        let dishes = store.repository.dishes(entry?.dishIDs ?? [])
        return Button {
            store.selectedDate = Date()
            store.selectedMeal = meal
            store.selectedTab = .menu
        } label: {
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 13, style: .continuous)
                        .fill(meal == currentMeal ? Theme.accentSoft : Theme.primarySoft.opacity(0.7))
                        .frame(width: 40, height: 40)
                    Text(meal.shortTitle)
                        .font(.traySerif(17, weight: .bold))
                        .foregroundStyle(meal == currentMeal ? Theme.accent : Theme.primary)
                }

                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(meal.title)
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                        if meal == currentMeal {
                            TagChip(text: "当前", tint: Theme.accent)
                        }
                    }
                    Text(entry?.time ?? meal.defaultTime)
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.muted)
                    Text(dishes.prefix(3).map(\.name).joined(separator: " · "))
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.muted)
                        .lineLimit(1)
                }

                Spacer(minLength: 6)

                VStack(alignment: .trailing, spacing: 4) {
                    Text("\(dishes.count) 道")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(Theme.primary)
                    Image(systemName: "chevron.right")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Theme.muted.opacity(0.6))
                }
            }
            .padding(.vertical, 11)
            .contentShape(Rectangle())
        }
        .buttonStyle(PressableButtonStyle())
    }

    // MARK: - Transparency

    private var transparencyCard: some View {
        let meta = store.repository.meta
        return VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.shield")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.primary)
                Text("食堂公示")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Spacer()
                Text("今日")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Theme.muted)
            }

            HStack(spacing: 0) {
                stat(value: "\(Int(meta.oilPerPerson))g", label: "人均用油", symbol: "drop")
                divider
                stat(value: "\(String(format: "%.1f", meta.saltPerPerson))g", label: "人均用盐", symbol: "cube")
                divider
                stat(value: "\(meta.traceBatches) 批", label: "食材溯源", symbol: "leaf")
            }

            Text(meta.note)
                .font(.system(size: 11))
                .foregroundStyle(Theme.muted)
                .lineSpacing(3)
        }
        .trayCard(padding: 16)
    }

    private func stat(value: String, label: String, symbol: String) -> some View {
        VStack(spacing: 5) {
            HStack(spacing: 4) {
                Image(systemName: symbol)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(Theme.sage)
                Text(value)
                    .font(.trayNumber(16))
                    .foregroundStyle(Theme.ink)
            }
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(Theme.muted)
        }
        .frame(maxWidth: .infinity)
    }

    private var divider: some View {
        Rectangle()
            .fill(Theme.line)
            .frame(width: 1, height: 30)
    }
}
