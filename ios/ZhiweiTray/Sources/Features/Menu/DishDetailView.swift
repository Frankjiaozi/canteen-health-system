import SwiftUI
import TrayCore

struct DishDetailView: View {
    @EnvironmentObject private var store: TrayStore
    @Environment(\.dismiss) private var dismiss

    let dish: Dish
    let meal: MealType

    private var blocked: Bool {
        !Set(dish.allergens).isDisjoint(with: store.profile.allergens)
    }

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(spacing: 20) {
                hero
                nutritionSection
                ingredientSection
                allergenSection
                noteSection
            }
            .padding(.bottom, 120)
        }
        .background(Theme.background.ignoresSafeArea())
        .ignoresSafeArea(edges: .top)
        .safeAreaInset(edge: .bottom) {
            bottomBar
        }
        .presentationCornerRadius(28)
    }

    private var hero: some View {
        ZStack(alignment: .bottomLeading) {
            DishImageView(name: dish.image, symbol: dish.category.symbol)
                .frame(height: 330)
                .frame(maxWidth: .infinity)
                .overlay(
                    LinearGradient(
                        colors: [.black.opacity(0.05), .black.opacity(0.62)],
                        startPoint: .center,
                        endPoint: .bottom
                    )
                )

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    ForEach(dish.tags.prefix(3), id: \.self) { tag in
                        Text(tag)
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.white.opacity(0.18), in: Capsule())
                    }
                }
                Text(dish.name)
                    .font(.traySerif(30, weight: .bold))
                    .foregroundStyle(.white)
                HStack(spacing: 6) {
                    Image(systemName: "mappin.and.ellipse")
                        .font(.system(size: 10))
                    Text(dish.stall)
                        .font(.system(size: 11))
                }
                .foregroundStyle(.white.opacity(0.82))
            }
            .padding(22)

            VStack {
                HStack {
                    Spacer()
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundStyle(Theme.ink)
                            .frame(width: 34, height: 34)
                            .background(.white.opacity(0.92), in: Circle())
                    }
                    .buttonStyle(PressableButtonStyle())
                }
                Spacer()
            }
            .padding(.top, 58)
            .padding(.horizontal, 18)
        }
    }

    private var nutritionSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionHeader(title: "每份营养", subtitle: "标准份量")
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 3), spacing: 10) {
                nutrient("热量", "\(Int(dish.nutrition.calories.rounded()))", "kcal", Theme.accent)
                nutrient("蛋白质", String(format: "%.1f", dish.nutrition.protein), "g", Theme.primary)
                nutrient("脂肪", String(format: "%.1f", dish.nutrition.fat), "g", Theme.gold)
                nutrient("碳水", String(format: "%.1f", dish.nutrition.carbs), "g", Color(hex: 0x8A6C4F))
                nutrient("膳食纤维", String(format: "%.1f", dish.nutrition.fiber), "g", Theme.sage)
                nutrient("钠", "\(Int(dish.nutrition.sodium.rounded()))", "mg", Color(hex: 0x7A8B9A))
            }
        }
        .padding(.horizontal, Theme.pagePadding)
    }

    private func nutrient(_ title: String, _ value: String, _ unit: String, _ tint: Color) -> some View {
        VStack(spacing: 4) {
            Text(title)
                .font(.system(size: 10))
                .foregroundStyle(Theme.muted)
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text(value)
                    .font(.trayNumber(18))
                    .foregroundStyle(Theme.ink)
                Text(unit)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(Theme.muted)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
        .overlay(alignment: .bottom) {
            Capsule()
                .fill(tint)
                .frame(width: 22, height: 2)
                .padding(.bottom, 6)
        }
    }

    private var ingredientSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionHeader(title: "主要食材")
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 74), spacing: 8)], alignment: .leading, spacing: 8) {
                ForEach(dish.ingredients, id: \.self) { item in
                    Text(item)
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.ink.opacity(0.8))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(Theme.card, in: Capsule())
                }
            }
        }
        .padding(.horizontal, Theme.pagePadding)
    }

    private var allergenSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "过敏原")
            if dish.allergens.isEmpty {
                Label("未标注常见过敏原", systemImage: "checkmark.circle")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.primary)
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            } else {
                HStack(spacing: 7) {
                    ForEach(dish.allergens, id: \.self) { item in
                        TagChip(text: item, tint: blocked ? Theme.accent : Theme.muted, filled: blocked)
                    }
                    Spacer()
                }
                .padding(14)
                .background(blocked ? Theme.accentSoft : Theme.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                if blocked {
                    Text("你设置了避开这些过敏原，建议换一道菜。")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.accent)
                }
            }
        }
        .padding(.horizontal, Theme.pagePadding)
    }

    private var noteSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionHeader(title: "后厨备注")
            Text(dish.note)
                .font(.system(size: 13))
                .foregroundStyle(Theme.muted)
                .lineSpacing(4)
            Text("营养值按标准份量核算，实际以当日出餐为准。")
                .font(.system(size: 10))
                .foregroundStyle(Theme.muted.opacity(0.8))
        }
        .padding(.horizontal, Theme.pagePadding)
    }

    private var bottomBar: some View {
        HStack(spacing: 12) {
            Button {
                store.toggleFavorite(dish)
            } label: {
                Image(systemName: store.isFavorite(dish) ? "heart.fill" : "heart")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundStyle(store.isFavorite(dish) ? Theme.accent : Theme.muted)
                    .frame(width: 48, height: 48)
                    .background(Theme.card, in: Circle())
            }
            .buttonStyle(PressableButtonStyle())

            Button {
                store.addToTray(dish, meal: meal)
                store.toast = "已加入\(meal.title)餐盘"
            } label: {
                HStack {
                    Text("加入\(meal.title)餐盘")
                    Spacer()
                    Text("¥\(String(format: "%.1f", dish.price))")
                        .font(.trayNumber(15))
                }
                .padding(.horizontal, 20)
            }
            .buttonStyle(PrimaryButtonStyle())
        }
        .padding(.horizontal, Theme.pagePadding)
        .padding(.top, 10)
        .padding(.bottom, 6)
        .background(.ultraThinMaterial)
    }
}
