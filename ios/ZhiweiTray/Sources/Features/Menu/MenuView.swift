import SwiftUI
import TrayCore

struct MenuView: View {
    @EnvironmentObject private var store: TrayStore
    @State private var query = ""
    @State private var category: DishCategory?
    @State private var avoidAllergens = false
    @State private var detailDish: Dish?

    private var days: [MenuDay] {
        store.repository.weekMenus(containing: AppClock.now)
    }

    private var menu: MenuDay {
        store.menu(for: store.selectedDate)
    }

    private var dishes: [Dish] {
        let base = store.repository.dishes(menu.meal(store.selectedMeal)?.dishIDs ?? [])
        return base.filter { dish in
            if let category, dish.category != category { return false }
            if avoidAllergens, !Set(dish.allergens).isDisjoint(with: store.profile.allergens) { return false }
            if !query.isEmpty {
                let haystack = dish.name + dish.tags.joined() + dish.ingredients.joined()
                if !haystack.localizedCaseInsensitiveContains(query) { return false }
            }
            return true
        }
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                header
                dayStrip
                MealPicker(selection: $store.selectedMeal)
                    .padding(.top, 14)
                    .padding(.horizontal, Theme.pagePadding)
                searchRow
                categoryRow
                dishList
            }
            .background(Theme.background.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .sheet(item: $detailDish) { dish in
                DishDetailView(dish: dish, meal: store.selectedMeal)
                    .environmentObject(store)
            }
            .onChange(of: store.selectedTab) { _, tab in
                if tab == .menu, Calendar.current.startOfDay(for: store.selectedDate) < Calendar.current.startOfDay(for: AppClock.now) {
                    store.selectedDate = AppClock.now
                }
            }
        }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("本周菜单")
                    .font(.traySerif(28, weight: .bold))
                    .foregroundStyle(Theme.ink)
                Text("\(store.repository.canteen.school) · \(store.repository.canteen.updated)")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.muted)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text("\(dishes.count)")
                    .font(.trayNumber(18))
                    .foregroundStyle(Theme.primary)
                Text("道在售")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.muted)
            }
        }
        .padding(.horizontal, Theme.pagePadding)
        .padding(.top, 10)
        .padding(.bottom, 12)
    }

    private var dayStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(days) { day in
                    let isSelected = Calendar.current.isDate(day.date, inSameDayAs: store.selectedDate)
                    let isToday = Calendar.current.isDateInToday(day.date)
                    Button {
                        withAnimation(.spring(response: 0.28, dampingFraction: 0.8)) {
                            store.selectedDate = day.date
                        }
                    } label: {
                        VStack(spacing: 4) {
                            Text(isToday ? "今天" : day.label.replacingOccurrences(of: "周", with: ""))
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(isSelected ? .white.opacity(0.8) : Theme.muted)
                            Text("\(Calendar.current.component(.day, from: day.date))")
                                .font(.trayNumber(17))
                                .foregroundStyle(isSelected ? .white : Theme.ink)
                        }
                        .frame(width: 46, height: 54)
                        .background(isSelected ? Theme.primary : Theme.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 16, style: .continuous)
                                .stroke(isSelected ? .clear : Theme.line.opacity(0.7), lineWidth: 1)
                        )
                    }
                    .buttonStyle(PressableButtonStyle())
                }
            }
            .padding(.horizontal, Theme.pagePadding)
        }
    }

    private var searchRow: some View {
        HStack(spacing: 10) {
            HStack(spacing: 7) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.muted)
                TextField("搜菜品、食材", text: $query)
                    .font(.system(size: 14))
                    .textInputAutocapitalization(.never)
                    .submitLabel(.search)
                if !query.isEmpty {
                    Button {
                        query = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(Theme.muted.opacity(0.7))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .frame(height: 40)
            .background(Theme.card, in: Capsule())

            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    avoidAllergens.toggle()
                }
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: avoidAllergens ? "checkmark.shield.fill" : "shield")
                        .font(.system(size: 11, weight: .semibold))
                    Text("避敏")
                        .font(.system(size: 12, weight: .semibold))
                }
                .foregroundStyle(avoidAllergens ? .white : Theme.primary)
                .padding(.horizontal, 12)
                .frame(height: 40)
                .background(avoidAllergens ? Theme.primary : Theme.card, in: Capsule())
            }
            .buttonStyle(PressableButtonStyle())
        }
        .padding(.horizontal, Theme.pagePadding)
        .padding(.top, 12)
    }

    private var categoryRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                categoryChip(nil, title: "全部")
                ForEach(DishCategory.allCases, id: \.self) { item in
                    categoryChip(item, title: item.title)
                }
            }
            .padding(.horizontal, Theme.pagePadding)
        }
        .padding(.top, 12)
        .padding(.bottom, 4)
    }

    private func categoryChip(_ item: DishCategory?, title: String) -> some View {
        let selected = category == item
        return Button {
            withAnimation(.spring(response: 0.25, dampingFraction: 0.85)) {
                category = item
            }
        } label: {
            Text(title)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(selected ? Theme.primary : Theme.muted)
                .padding(.horizontal, 13)
                .padding(.vertical, 8)
                .background(selected ? Theme.primarySoft : Color.clear, in: Capsule())
                .overlay(Capsule().stroke(selected ? .clear : Theme.line, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private var dishList: some View {
        ScrollView(showsIndicators: false) {
            LazyVStack(spacing: 11) {
                if dishes.isEmpty {
                    EmptyStateView(
                        symbol: "fork.knife.circle",
                        title: "这个时段没有匹配的菜",
                        message: "换个餐次或清除筛选条件再看看。"
                    )
                } else {
                    ForEach(dishes) { dish in
                        dishRow(dish)
                    }
                }
            }
            .padding(.horizontal, Theme.pagePadding)
            .padding(.top, 10)
            .padding(.bottom, 110)
        }
    }

    private func dishRow(_ dish: Dish) -> some View {
        let blocked = !Set(dish.allergens).isDisjoint(with: store.profile.allergens)
        return HStack(spacing: 13) {
            Button {
                detailDish = dish
            } label: {
                HStack(spacing: 13) {
                    DishImageView(name: dish.image, symbol: dish.category.symbol)
                        .frame(width: 86, height: 86)
                        .clipShape(RoundedRectangle(cornerRadius: 17, style: .continuous))

                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 6) {
                            Text(dish.name)
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundStyle(Theme.ink)
                            if blocked {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .font(.system(size: 10))
                                    .foregroundStyle(Theme.accent)
                            }
                        }
                        Text(dish.stall)
                            .font(.system(size: 10))
                            .foregroundStyle(Theme.muted)
                        HStack(spacing: 7) {
                            Text("\(Int(dish.nutrition.calories.rounded())) kcal")
                            Text("蛋白 \(String(format: "%.1f", dish.nutrition.protein))g")
                        }
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(Theme.primary.opacity(0.85))

                        HStack(spacing: 5) {
                            ForEach(dish.tags.prefix(2), id: \.self) { tag in
                                TagChip(text: tag, tint: tag == "微辣" ? Theme.accent : Theme.primary)
                            }
                            if blocked {
                                TagChip(text: "含\(dish.allergens.joined(separator: "/"))", tint: Theme.accent, filled: true)
                            } else if let first = dish.allergens.first {
                                Text("含\(first)")
                                    .font(.system(size: 10))
                                    .foregroundStyle(Theme.muted)
                            }
                        }
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(PressableButtonStyle())

            VStack(alignment: .trailing, spacing: 10) {
                Text("¥\(String(format: "%.1f", dish.price))")
                    .font(.trayNumber(15))
                    .foregroundStyle(Theme.ink)
                Button {
                    store.addToTray(dish, meal: store.selectedMeal)
                    store.toast = "已加入\(store.selectedMeal.title)餐盘"
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 30, height: 30)
                        .background(Theme.primary, in: Circle())
                }
                .buttonStyle(PressableButtonStyle())
            }
        }
        .trayCard(padding: 11, radius: 20)
    }
}
