import SwiftUI
import TrayCore

struct ProfileView: View {
    @EnvironmentObject private var store: TrayStore
    @State private var showResetAlert = false
    @State private var showAbout = false

    var body: some View {
        NavigationStack {
            ScrollView(showsIndicators: false) {
                VStack(spacing: 16) {
                    header
                    goalCard
                    targetCard
                    allergenCard
                    favoritesCard
                    privacyCard
                }
                .padding(.horizontal, Theme.pagePadding)
                .padding(.top, 10)
                .padding(.bottom, 110)
            }
            .background(Theme.background.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .alert("重置演示数据？", isPresented: $showResetAlert) {
                Button("取消", role: .cancel) {}
                Button("重置", role: .destructive) { store.resetDemo() }
            } message: {
                Text("会清空本机的记录、收藏和设置，并恢复示例数据。")
            }
            .sheet(isPresented: $showAbout) {
                aboutSheet
                    .presentationDetents([.medium])
                    .presentationCornerRadius(26)
            }
        }
    }

    private var header: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle()
                    .fill(Theme.primarySoft)
                    .frame(width: 58, height: 58)
                Text("味")
                    .font(.traySerif(26, weight: .bold))
                    .foregroundStyle(Theme.primary)
            }
            VStack(alignment: .leading, spacing: 5) {
                TextField("你的称呼", text: $store.profile.name)
                    .font(.traySerif(22, weight: .bold))
                    .foregroundStyle(Theme.ink)
                    .textFieldStyle(.plain)
                    .onSubmit { store.save() }
                Text("示例大学 · 第一食堂 · 离线模式")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.muted)
            }
            Spacer()
        }
        .padding(.vertical, 8)
    }

    private var goalCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionHeader(title: "我的目标", subtitle: "影响每餐的推荐")
            HStack(spacing: 9) {
                ForEach(Goal.allCases) { goal in
                    let selected = store.profile.goal == goal
                    Button {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                            store.profile.goal = goal
                            store.save()
                        }
                    } label: {
                        VStack(alignment: .leading, spacing: 7) {
                            Image(systemName: goal.symbol)
                                .font(.system(size: 16, weight: .medium))
                                .foregroundStyle(selected ? .white : Theme.primary)
                            Text(goal.title)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(selected ? .white : Theme.ink)
                            Text(goal.subtitle)
                                .font(.system(size: 9))
                                .foregroundStyle(selected ? .white.opacity(0.75) : Theme.muted)
                                .lineLimit(2)
                                .multilineTextAlignment(.leading)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .background(selected ? Theme.primary : Theme.background, in: RoundedRectangle(cornerRadius: 17, style: .continuous))
                    }
                    .buttonStyle(PressableButtonStyle())
                }
            }
        }
        .trayCard()
    }

    private var targetCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "每日目标")

            VStack(spacing: 7) {
                HStack {
                    Text("能量目标")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Text("\(Int(store.profile.calorieTarget)) kcal")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .foregroundStyle(Theme.primary)
                }
                Slider(value: $store.profile.calorieTarget, in: 1600...2600, step: 50, onEditingChanged: { _ in store.save() })
                    .tint(Theme.primary)
            }

            VStack(spacing: 7) {
                HStack {
                    Text("每餐预算")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Text("¥\(Int(store.profile.budgetPerMeal))")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .foregroundStyle(Theme.accent)
                }
                Slider(value: $store.profile.budgetPerMeal, in: 8...25, step: 1, onEditingChanged: { _ in store.save() })
                    .tint(Theme.accent)
            }
        }
        .trayCard()
    }

    private var allergenCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionHeader(title: "需要避开的过敏原", subtitle: "推荐会自动排除")
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 78), spacing: 8)], alignment: .leading, spacing: 8) {
                ForEach(Allergen.all, id: \.self) { item in
                    let selected = store.profile.allergens.contains(item)
                    Button {
                        if selected {
                            store.profile.allergens.remove(item)
                        } else {
                            store.profile.allergens.insert(item)
                        }
                        store.save()
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: selected ? "checkmark" : "plus")
                                .font(.system(size: 9, weight: .bold))
                            Text(item)
                                .font(.system(size: 12, weight: .medium))
                        }
                        .foregroundStyle(selected ? .white : Theme.muted)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(selected ? Theme.accent : Theme.background, in: Capsule())
                    }
                    .buttonStyle(PressableButtonStyle())
                }
            }
        }
        .trayCard()
    }

    private var favoritesCard: some View {
        let favorites = store.profile.favorites.compactMap { store.repository.dish($0) }
        return VStack(alignment: .leading, spacing: 12) {
            SectionHeader(title: "我的收藏", subtitle: "\(favorites.count) 道")
            if favorites.isEmpty {
                Text("在菜品详情里点 ♥ 收藏常吃的菜。")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.muted)
                    .padding(.vertical, 6)
            } else {
                ForEach(favorites) { dish in
                    HStack(spacing: 11) {
                        DishImageView(name: dish.image, symbol: dish.category.symbol)
                            .frame(width: 46, height: 46)
                            .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(dish.name)
                                .font(.system(size: 13, weight: .medium))
                                .foregroundStyle(Theme.ink)
                            Text("\(Int(dish.nutrition.calories.rounded())) kcal · ¥\(String(format: "%.1f", dish.price))")
                                .font(.system(size: 10, design: .rounded))
                                .foregroundStyle(Theme.muted)
                        }
                        Spacer()
                        Button {
                            store.toggleFavorite(dish)
                        } label: {
                            Image(systemName: "heart.fill")
                                .font(.system(size: 12))
                                .foregroundStyle(Theme.accent)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .trayCard()
    }

    private var privacyCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "lock.shield")
                    .font(.system(size: 14))
                    .foregroundStyle(Theme.primary)
                Text("数据与隐私")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Theme.ink)
            }
            Text("餐盘是离线优先的示例应用：菜单与营养数据随包内置，记录和设置只写入本机，不上传、不登录、不申请网络权限。")
                .font(.system(size: 11))
                .foregroundStyle(Theme.muted)
                .lineSpacing(3)

            HStack(spacing: 10) {
                Button {
                    showAbout = true
                } label: {
                    Text("关于餐盘")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Theme.primary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(Theme.primarySoft, in: Capsule())
                }
                .buttonStyle(PressableButtonStyle())

                Button {
                    showResetAlert = true
                } label: {
                    Text("重置演示数据")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Theme.accent)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(Theme.accentSoft, in: Capsule())
                }
                .buttonStyle(PressableButtonStyle())
            }
        }
        .trayCard()
    }

    private var aboutSheet: some View {
        ScrollView {
            VStack(spacing: 12) {
                ZStack {
                    Circle()
                        .fill(Theme.primarySoft)
                        .frame(width: 64, height: 64)
                    Text("味")
                        .font(.traySerif(28, weight: .bold))
                        .foregroundStyle(Theme.primary)
                }
                Text("知味 · 餐盘")
                    .font(.traySerif(22, weight: .bold))
                    .foregroundStyle(Theme.ink)
                Text("版本 1.0 (1)")
                    .font(.system(size: 11, design: .rounded))
                    .foregroundStyle(Theme.muted)

                Text("把食堂后厨的营养账本，变成学生看得懂的一餐。菜单、营养与过敏原由学校食堂维护；餐盘只做本地推荐，不替代专业营养建议。")
                    .font(.system(size: 12))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Theme.muted)
                    .lineSpacing(4)
                    .padding(.horizontal, 24)

                HStack(spacing: 6) {
                    TagChip(text: "SwiftUI")
                    TagChip(text: "离线优先")
                    TagChip(text: "xtool")
                }
                .padding(.top, 4)

                Text("演示数据 · 2026")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.muted.opacity(0.7))
                    .padding(.top, 8)
            }
            .padding(24)
        }
        .background(Theme.background)
    }
}
