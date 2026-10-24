import SwiftUI
import TrayCore

extension DishCategory: Identifiable {
    public var id: String { rawValue }
}

struct TrayView: View {
    @EnvironmentObject private var store: TrayStore
    @State private var swapCategory: DishCategory?

    var body: some View {
        NavigationStack {
            ScrollView(showsIndicators: false) {
                VStack(spacing: 16) {
                    header
                    if store.tray.isEmpty {
                        emptyState
                    } else {
                        totalsCard
                        slotsCard
                        shuffleStrip
                        saveButton
                    }
                }
                .padding(.horizontal, Theme.pagePadding)
                .padding(.top, 10)
                .padding(.bottom, 110)
            }
            .background(Theme.background.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .sheet(item: $swapCategory) { category in
                SwapSheet(category: category)
                    .environmentObject(store)
            }
        }
    }

    private var header: some View {
        VStack(spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("我的餐盘")
                        .font(.traySerif(28, weight: .bold))
                        .foregroundStyle(Theme.ink)
                    Text("按你的目标与预算实时计算")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.muted)
                }
                Spacer()
                if !store.tray.isEmpty {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            store.clearTray()
                        }
                    } label: {
                        Text("清空")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(Theme.muted)
                    }
                    .buttonStyle(.plain)
                }
            }
            MealPicker(selection: $store.trayMeal)
        }
    }

    // MARK: - Empty

    private var emptyState: some View {
        VStack(spacing: 16) {
            VStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(Theme.primarySoft)
                        .frame(width: 84, height: 84)
                    Image(systemName: "circle.hexagongrid")
                        .font(.system(size: 34, weight: .light))
                        .foregroundStyle(Theme.primary)
                }
                Text("餐盘还是空的")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Text("让知味按你的营养目标和预算配一套，\n也可以从菜单里自己挑。")
                    .font(.system(size: 12))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Theme.muted)
                    .lineSpacing(3)
            }
            .padding(.top, 12)

            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("试试这几套")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Button {
                        withAnimation { store.shuffleSuggestions() }
                    } label: {
                        Text("换一批")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(Theme.primary)
                    }
                    .buttonStyle(.plain)
                }

                ForEach(store.recommendations(for: store.trayMeal, limit: 3)) { combo in
                    suggestionCard(combo)
                }
            }

            Button {
                store.selectedTab = .menu
            } label: {
                Text("去菜单挑选")
            }
            .buttonStyle(PrimaryButtonStyle(color: Theme.primary))
            .padding(.top, 4)
        }
    }

    private func suggestionCard(_ combo: Combo) -> some View {
        Button {
            withAnimation(.spring(response: 0.35, dampingFraction: 0.85)) {
                store.apply(combo)
            }
        } label: {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 7) {
                    ForEach(combo.dishes.prefix(4)) { dish in
                        DishImageView(name: dish.image, symbol: dish.category.symbol)
                            .frame(width: 46, height: 46)
                            .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 1) {
                        Text("¥\(String(format: "%.1f", combo.price))")
                            .font(.trayNumber(15))
                            .foregroundStyle(Theme.ink)
                        Text("\(Int(combo.nutrition.calories.rounded())) kcal")
                            .font(.system(size: 10, design: .rounded))
                            .foregroundStyle(Theme.muted)
                    }
                }
                Text(combo.dishes.map(\.name).joined(separator: " · "))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                HStack(spacing: 5) {
                    TagChip(text: "蛋白 \(Int(combo.nutrition.protein.rounded()))g", tint: Theme.primary)
                    TagChip(text: "评分 \(combo.healthScore)", tint: Theme.gold)
                }
            }
            .trayCard(padding: 13, radius: 18)
        }
        .buttonStyle(PressableButtonStyle())
    }

    // MARK: - Totals

    private var totalsCard: some View {
        let target = NutritionMath.targets(for: store.profile, meal: store.trayMeal)
        let nutrition = store.trayNutrition
        let overBudget = store.trayPrice > store.profile.budgetPerMeal
        return VStack(spacing: 16) {
            HStack(spacing: 18) {
                ZStack {
                    ProgressRing(
                        progress: Double(store.trayHealthScore) / 100,
                        lineWidth: 8,
                        colors: [Theme.accent, Theme.gold]
                    )
                    VStack(spacing: 0) {
                        Text("\(store.trayHealthScore)")
                            .font(.trayNumber(24))
                            .foregroundStyle(Theme.ink)
                        Text("评分")
                            .font(.system(size: 9))
                            .foregroundStyle(Theme.muted)
                    }
                }
                .frame(width: 86, height: 86)

                VStack(alignment: .leading, spacing: 9) {
                    HStack {
                        Text("合计")
                            .font(.system(size: 12))
                            .foregroundStyle(Theme.muted)
                        Spacer()
                        Text("¥\(String(format: "%.1f", store.trayPrice))")
                            .font(.trayNumber(20))
                            .foregroundStyle(overBudget ? Theme.accent : Theme.ink)
                        Text("/ ¥\(Int(store.profile.budgetPerMeal))")
                            .font(.system(size: 11, design: .rounded))
                            .foregroundStyle(Theme.muted)
                    }
                    GeometryReader { proxy in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Theme.line.opacity(0.7))
                            Capsule()
                                .fill(overBudget ? Theme.accent : Theme.primary)
                                .frame(width: min(proxy.size.width, proxy.size.width * store.trayPrice / max(store.profile.budgetPerMeal, 1)))
                        }
                    }
                    .frame(height: 6)

                    HStack(spacing: 10) {
                        Text("\(Int(nutrition.calories.rounded())) kcal")
                            .font(.system(size: 11, weight: .semibold, design: .rounded))
                            .foregroundStyle(Theme.primary)
                        Text("蛋白 \(Int(nutrition.protein.rounded()))g")
                            .font(.system(size: 11, design: .rounded))
                            .foregroundStyle(Theme.muted)
                        Text("纤维 \(String(format: "%.1f", nutrition.fiber))g")
                            .font(.system(size: 11, design: .rounded))
                            .foregroundStyle(Theme.muted)
                    }
                }
            }

            VStack(spacing: 9) {
                MacroBar(title: "热量", value: nutrition.calories, target: target.calories, unit: " kcal", tint: Theme.accent)
                MacroBar(title: "蛋白质", value: nutrition.protein, target: target.protein, unit: "g", tint: Theme.primary)
                MacroBar(title: "钠", value: nutrition.sodium, target: target.sodium, unit: "mg", tint: Theme.sage)
            }
        }
        .trayCard()
    }

    // MARK: - Slots

    private var slotsCard: some View {
        VStack(spacing: 0) {
            HStack {
                SectionHeader(title: "搭配明细")
                Text("共 \(store.tray.count) 道")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.muted)
            }
            .padding(.bottom, 4)

            ForEach(store.trayMeal.slots, id: \.self) { category in
                if let dish = store.tray.first(where: { $0.category == category }) {
                    slotRow(dish, category: category)
                } else {
                    emptySlotRow(category)
                }
            }
        }
        .trayCard(padding: 15)
    }

    private func slotRow(_ dish: Dish, category: DishCategory) -> some View {
        HStack(spacing: 12) {
            DishImageView(name: dish.image, symbol: category.symbol)
                .frame(width: 58, height: 58)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

            VStack(alignment: .leading, spacing: 3) {
                Text(category.title)
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(Theme.sage)
                    .textCase(.uppercase)
                    .tracking(0.8)
                Text(dish.name)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Text("\(Int(dish.nutrition.calories.rounded())) kcal · 蛋白 \(String(format: "%.1f", dish.nutrition.protein))g · ¥\(String(format: "%.1f", dish.price))")
                    .font(.system(size: 10, design: .rounded))
                    .foregroundStyle(Theme.muted)
            }

            Spacer(minLength: 4)

            Button {
                swapCategory = category
            } label: {
                Text("换")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.primary)
                    .frame(width: 34, height: 30)
                    .background(Theme.primarySoft, in: Capsule())
            }
            .buttonStyle(.plain)

            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    store.removeFromTray(dish)
                }
            } label: {
                Image(systemName: "trash")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Theme.muted)
                    .frame(width: 30, height: 30)
            }
            .buttonStyle(.plain)
        }
        .padding(.vertical, 9)
    }

    private func emptySlotRow(_ category: DishCategory) -> some View {
        Button {
            swapCategory = category
        } label: {
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(Theme.line, style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                        .frame(width: 58, height: 58)
                    Image(systemName: category.symbol)
                        .font(.system(size: 16, weight: .light))
                        .foregroundStyle(Theme.muted.opacity(0.6))
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text(category.title)
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(Theme.sage)
                        .textCase(.uppercase)
                        .tracking(0.8)
                    Text("加一道\(category.title)")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Theme.muted)
                }
                Spacer()
                Image(systemName: "plus.circle")
                    .font(.system(size: 16))
                    .foregroundStyle(Theme.primary)
            }
            .padding(.vertical, 9)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: - Shuffle & save

    private var shuffleStrip: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("换一套")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Spacer()
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) { store.shuffleSuggestions() }
                } label: {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Theme.primary)
                }
                .buttonStyle(.plain)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(store.recommendations(for: store.trayMeal, limit: 4)) { combo in
                        Button {
                            withAnimation(.spring(response: 0.35, dampingFraction: 0.85)) {
                                store.apply(combo)
                            }
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(spacing: 4) {
                                    ForEach(combo.dishes.prefix(3)) { dish in
                                        DishImageView(name: dish.image, symbol: dish.category.symbol)
                                            .frame(width: 34, height: 34)
                                            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                                    }
                                }
                                Text("¥\(String(format: "%.1f", combo.price)) · \(Int(combo.nutrition.calories.rounded())) kcal")
                                    .font(.system(size: 10, weight: .medium, design: .rounded))
                                    .foregroundStyle(Theme.ink)
                                Text(combo.dishes.first?.name ?? "")
                                    .font(.system(size: 10))
                                    .foregroundStyle(Theme.muted)
                                    .lineLimit(1)
                            }
                            .frame(width: 128, alignment: .leading)
                            .padding(10)
                            .background(Theme.card, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 15, style: .continuous)
                                    .stroke(Theme.line, lineWidth: 1)
                            )
                        }
                        .buttonStyle(PressableButtonStyle())
                    }
                }
            }
        }
    }

    private var saveButton: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.25)) {
                _ = store.saveTray()
            }
        } label: {
            HStack {
                Image(systemName: "checkmark")
                    .font(.system(size: 13, weight: .bold))
                Text("记录这一餐")
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(PrimaryButtonStyle())
        .padding(.top, 4)
    }
}

// MARK: - Swap sheet

struct SwapSheet: View {
    @EnvironmentObject private var store: TrayStore
    @Environment(\.dismiss) private var dismiss

    let category: DishCategory

    private var alternatives: [Dish] {
        let combo = Combo(meal: store.trayMeal, dishes: store.tray, score: 0, reasons: [])
        return ComboEngine.alternatives(
            for: category,
            in: combo,
            pool: store.pool(for: store.trayMeal),
            meal: store.trayMeal,
            profile: store.profile
        )
    }

    var body: some View {
        NavigationStack {
            ScrollView(showsIndicators: false) {
                LazyVStack(spacing: 10) {
                    if alternatives.isEmpty {
                        EmptyStateView(
                            symbol: "leaf.circle",
                            title: "暂时没有可替换的\(category.title)",
                            message: "试试换一个餐次，或先清空过敏原筛选。"
                        )
                    }
                    ForEach(alternatives) { dish in
                        Button {
                            store.addToTray(dish, meal: store.trayMeal)
                            dismiss()
                        } label: {
                            HStack(spacing: 12) {
                                DishImageView(name: dish.image, symbol: dish.category.symbol)
                                    .frame(width: 64, height: 64)
                                    .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(dish.name)
                                        .font(.system(size: 15, weight: .semibold))
                                        .foregroundStyle(Theme.ink)
                                    Text("\(Int(dish.nutrition.calories.rounded())) kcal · 蛋白 \(String(format: "%.1f", dish.nutrition.protein))g")
                                        .font(.system(size: 11, design: .rounded))
                                        .foregroundStyle(Theme.muted)
                                    HStack(spacing: 5) {
                                        ForEach(dish.tags.prefix(2), id: \.self) { tag in
                                            TagChip(text: tag)
                                        }
                                    }
                                }
                                Spacer()
                                Text("¥\(String(format: "%.1f", dish.price))")
                                    .font(.trayNumber(14))
                                    .foregroundStyle(Theme.ink)
                            }
                            .trayCard(padding: 10, radius: 18)
                        }
                        .buttonStyle(PressableButtonStyle())
                    }
                }
                .padding(Theme.pagePadding)
            }
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("换一道\(category.title)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("关闭") { dismiss() }
                        .foregroundStyle(Theme.primary)
                }
            }
            .presentationDetents([.medium, .large])
            .presentationCornerRadius(26)
        }
    }
}
