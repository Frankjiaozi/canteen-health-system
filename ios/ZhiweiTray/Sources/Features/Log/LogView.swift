import SwiftUI
import TrayCore

struct LogView: View {
    @EnvironmentObject private var store: TrayStore
    @State private var selectedDate: Date = AppClock.now

    private var days: [(date: Date, summary: DaySummary)] {
        store.lastSevenDays()
    }

    private var summary: DaySummary {
        store.summary(for: selectedDate)
    }

    private var entries: [MealLogEntry] {
        store.entries(for: selectedDate)
    }

    var body: some View {
        NavigationStack {
            ScrollView(showsIndicators: false) {
                VStack(spacing: 16) {
                    header
                    chartCard
                    summaryCard
                    entriesSection
                    insightCard
                }
                .padding(.horizontal, Theme.pagePadding)
                .padding(.top, 10)
                .padding(.bottom, 110)
            }
            .background(Theme.background.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .onAppear {
                if !Calendar.current.isDateInToday(selectedDate) {
                    selectedDate = AppClock.now
                }
            }
        }
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 3) {
                Text("饮食记录")
                    .font(.traySerif(28, weight: .bold))
                    .foregroundStyle(Theme.ink)
                Text("每一餐都算数，数据只在本机")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.muted)
            }
            Spacer()
            HStack(spacing: 5) {
                Image(systemName: "flame.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.accent)
                Text("连续 \(streak) 天")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(Theme.ink)
            }
            .padding(.horizontal, 11)
            .padding(.vertical, 7)
            .background(Theme.accentSoft, in: Capsule())
        }
    }

    private var streak: Int {
        let calendar = Calendar.current
        var count = 0
        var day = calendar.startOfDay(for: AppClock.now)
        if store.summary(for: day).entries == 0 {
            day = calendar.date(byAdding: .day, value: -1, to: day) ?? day
        }
        while store.summary(for: day).entries > 0 {
            count += 1
            guard let previous = calendar.date(byAdding: .day, value: -1, to: day) else { break }
            day = previous
        }
        return count
    }

    // MARK: - Chart

    private var chartCard: some View {
        let values = days.map { $0.summary.nutrition.calories }
        let maxValue = max(NutritionMath.dailyTargets(for: store.profile).calories * 1.15, (values.max() ?? 0) * 1.1, 1)
        let target = NutritionMath.dailyTargets(for: store.profile).calories

        return VStack(alignment: .leading, spacing: 14) {
            HStack {
                SectionHeader(title: "近 7 天能量", subtitle: "kcal")
                Text("目标 \(Int(target))")
                    .font(.system(size: 10, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.muted)
            }

            GeometryReader { proxy in
                let barArea: CGFloat = 118
                let baseY: CGFloat = 148
                ZStack(alignment: .topLeading) {
                    Path { path in
                        let y = baseY - CGFloat(target / maxValue) * barArea
                        path.move(to: CGPoint(x: 0, y: y))
                        path.addLine(to: CGPoint(x: proxy.size.width, y: y))
                    }
                    .stroke(Theme.accent.opacity(0.5), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))

                    HStack(alignment: .bottom, spacing: 8) {
                        ForEach(days, id: \.date) { item in
                            let ratio = min(item.summary.nutrition.calories / maxValue, 1.05)
                            let isSelected = Calendar.current.isDate(item.date, inSameDayAs: selectedDate)
                            Button {
                                withAnimation(.easeInOut(duration: 0.2)) {
                                    selectedDate = item.date
                                }
                            } label: {
                                VStack(spacing: 6) {
                                    Text(item.summary.nutrition.calories > 0 ? "\(Int(item.summary.nutrition.calories.rounded()))" : "—")
                                        .font(.system(size: 8, weight: .semibold, design: .rounded))
                                        .foregroundStyle(isSelected ? Theme.primary : Theme.muted)
                                        .frame(height: 12)
                                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                                        .fill(
                                            isSelected
                                                ? LinearGradient(colors: [Theme.primary, Theme.sage], startPoint: .top, endPoint: .bottom)
                                                : LinearGradient(colors: [Theme.primarySoft, Theme.primarySoft], startPoint: .top, endPoint: .bottom)
                                        )
                                        .frame(height: max(4, CGFloat(ratio) * barArea))
                                    Text(weekdayLabel(item.date))
                                        .font(.system(size: 9, weight: isSelected ? .semibold : .regular))
                                        .foregroundStyle(isSelected ? Theme.ink : Theme.muted)
                                        .frame(height: 12)
                                }
                                .frame(maxWidth: .infinity)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .frame(maxHeight: .infinity, alignment: .bottom)
                }
            }
            .frame(height: 160)
        }
        .trayCard()
    }

    private func weekdayLabel(_ date: Date) -> String {
        if Calendar.current.isDateInToday(date) { return "今天" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_Hans_CN")
        formatter.dateFormat = "E"
        return formatter.string(from: date)
    }

    // MARK: - Summary

    private var summaryCard: some View {
        let target = NutritionMath.dailyTargets(for: store.profile)
        let isToday = Calendar.current.isDateInToday(selectedDate)
        return VStack(spacing: 14) {
            HStack {
                Text(isToday ? "今天" : dateTitle(selectedDate))
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Spacer()
                Text("\(entries.count) 餐 · ¥\(String(format: "%.1f", summary.price))")
                    .font(.system(size: 11, design: .rounded))
                    .foregroundStyle(Theme.muted)
            }

            HStack(spacing: 18) {
                ZStack {
                    ProgressRing(progress: summary.nutrition.calories / max(target.calories, 1), lineWidth: 8)
                    VStack(spacing: 0) {
                        Text("\(Int(summary.nutrition.calories.rounded()))")
                            .font(.trayNumber(20))
                            .foregroundStyle(Theme.ink)
                        Text("kcal")
                            .font(.system(size: 9))
                            .foregroundStyle(Theme.muted)
                    }
                }
                .frame(width: 86, height: 86)

                VStack(spacing: 10) {
                    MacroBar(title: "蛋白质", value: summary.nutrition.protein, target: target.protein, unit: "g", tint: Theme.primary)
                    MacroBar(title: "脂肪", value: summary.nutrition.fat, target: target.fat, unit: "g", tint: Theme.gold)
                    MacroBar(title: "碳水", value: summary.nutrition.carbs, target: target.carbs, unit: "g", tint: Theme.accent)
                }
            }
        }
        .trayCard()
    }

    private func dateTitle(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_Hans_CN")
        formatter.dateFormat = "M月d日"
        return formatter.string(from: date)
    }

    // MARK: - Entries

    private var entriesSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionHeader(title: "当日餐次")
                Button {
                    store.selectedDate = selectedDate
                    store.selectedMeal = TrayStore.mealForNow()
                    store.selectedTab = .menu
                } label: {
                    Text("去记录")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Theme.primary)
                }
                .buttonStyle(.plain)
            }

            if entries.isEmpty {
                VStack(spacing: 6) {
                    Text("这天还没有记录")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(Theme.ink)
                    Text("从菜单里挑一餐，或让知味帮你配一套。")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.muted)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 26)
                .background(Theme.card, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            } else {
                ForEach(entries) { entry in
                    entryCard(entry)
                }
            }
        }
    }

    private func entryCard(_ entry: MealLogEntry) -> some View {
        let dishes = store.dishes(for: entry)
        let nutrition = dishes.reduce(Nutrition.zero) { $0 + $1.nutrition }
        return VStack(alignment: .leading, spacing: 11) {
            HStack {
                Text(entry.meal.title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Text(entry.meal.defaultTime)
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.muted)
                Spacer()
                Text("\(Int(nutrition.calories.rounded())) kcal")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(Theme.primary)
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        store.delete(entry)
                    }
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.muted.opacity(0.7))
                }
                .buttonStyle(.plain)
            }

            HStack(spacing: 7) {
                ForEach(dishes.prefix(4)) { dish in
                    DishImageView(name: dish.image, symbol: dish.category.symbol)
                        .frame(width: 44, height: 44)
                        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text(dishes.map(\.name).joined(separator: " · "))
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.ink.opacity(0.8))
                        .lineLimit(2)
                    Text("蛋白 \(Int(nutrition.protein.rounded()))g · ¥\(String(format: "%.1f", dishes.reduce(0) { $0 + $1.price }))")
                        .font(.system(size: 10, design: .rounded))
                        .foregroundStyle(Theme.muted)
                }
                Spacer(minLength: 0)
            }
        }
        .trayCard(padding: 14, radius: 19)
    }

    // MARK: - Insight

    private var insightCard: some View {
        let met = store.proteinDaysMet()
        let avg = days.map(\.summary.nutrition.calories).reduce(0, +) / 7
        let spend = days.map(\.summary.price).reduce(0, +)
        return VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 7) {
                Image(systemName: "lightbulb")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.gold)
                Text("本周小结")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Theme.ink)
            }
            HStack(spacing: 0) {
                insight(value: "\(met)/7", label: "蛋白质达标")
                insightDivider
                insight(value: "\(Int(avg))", label: "日均 kcal")
                insightDivider
                insight(value: "¥\(Int(spend))", label: "本周餐费")
            }
            Text(met >= 4 ? "蛋白质完成得不错，继续保持蔬菜和汤的搭配。" : "本周蛋白质偏低，下一餐可以优先选鱼、鸡胸或豆腐。")
                .font(.system(size: 11))
                .foregroundStyle(Theme.muted)
                .lineSpacing(3)
        }
        .trayCard(padding: 16)
    }

    private func insight(value: String, label: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.trayNumber(17))
                .foregroundStyle(Theme.ink)
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(Theme.muted)
        }
        .frame(maxWidth: .infinity)
    }

    private var insightDivider: some View {
        Rectangle()
            .fill(Theme.line)
            .frame(width: 1, height: 26)
    }
}
