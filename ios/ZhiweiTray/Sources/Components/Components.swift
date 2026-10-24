import SwiftUI
import UIKit

enum DishImageStore {
    private static let cache = NSCache<NSString, UIImage>()

    private static var bundle: Bundle {
        #if SWIFT_PACKAGE
        return Bundle.module
        #else
        return Bundle.main
        #endif
    }

    static func image(named name: String) -> UIImage? {
        if let cached = cache.object(forKey: name as NSString) { return cached }
        guard
            let url = bundle.url(forResource: name, withExtension: "jpg"),
            let image = UIImage(contentsOfFile: url.path)
        else { return nil }
        cache.setObject(image, forKey: name as NSString)
        return image
    }
}

struct DishImageView: View {
    let name: String
    var symbol: String = "fork.knife"

    var body: some View {
        Group {
            if let image = DishImageStore.image(named: name) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                ZStack {
                    LinearGradient(
                        colors: [Theme.primarySoft, Theme.background],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                    Image(systemName: symbol)
                        .font(.system(size: 26, weight: .light))
                        .foregroundStyle(Theme.primary.opacity(0.45))
                }
            }
        }
        .clipped()
    }
}

struct TagChip: View {
    let text: String
    var tint: Color = Theme.primary
    var filled: Bool = false

    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .medium))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .foregroundStyle(filled ? .white : tint)
            .background(filled ? tint : tint.opacity(0.09), in: Capsule())
    }
}

struct ProgressRing: View {
    var progress: Double
    var lineWidth: CGFloat = 10
    var colors: [Color] = [Theme.primary, Theme.sage]

    var body: some View {
        ZStack {
            Circle()
                .stroke(Theme.primarySoft, lineWidth: lineWidth)
            Circle()
                .trim(from: 0, to: min(max(progress, 0), 1))
                .stroke(
                    AngularGradient(colors: colors, center: .center, startAngle: .degrees(-90), endAngle: .degrees(270)),
                    style: StrokeStyle(lineWidth: lineWidth, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .animation(.spring(response: 0.6, dampingFraction: 0.85), value: progress)
        }
    }
}

struct MacroBar: View {
    let title: String
    let value: Double
    let target: Double
    let unit: String
    var tint: Color

    private var progress: Double { min(max(value / max(target, 1), 0), 1) }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Theme.muted)
                Spacer()
                Text("\(Int(value.rounded())) / \(Int(target.rounded()))\(unit)")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(Theme.ink.opacity(0.75))
            }
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(tint.opacity(0.14))
                    Capsule()
                        .fill(tint)
                        .frame(width: max(4, proxy.size.width * progress))
                }
            }
            .frame(height: 6)
        }
    }
}

struct SectionHeader: View {
    let title: String
    var subtitle: String? = nil

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.ink)
            if let subtitle {
                Text(subtitle)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.muted)
            }
            Spacer()
        }
    }
}

struct ToastView: View {
    let text: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.white)
            Text(text)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(.white)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 11)
        .background(Theme.ink.opacity(0.92), in: Capsule())
        .shadow(color: .black.opacity(0.18), radius: 12, y: 6)
    }
}

struct MealPicker: View {
    @Binding var selection: MealType
    var compact: Bool = false

    var body: some View {
        HStack(spacing: 6) {
            ForEach(MealType.allCases) { meal in
                Button {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                        selection = meal
                    }
                } label: {
                    Text(meal.title)
                        .font(.system(size: compact ? 13 : 14, weight: .semibold))
                        .foregroundStyle(selection == meal ? .white : Theme.muted)
                        .padding(.horizontal, compact ? 14 : 18)
                        .padding(.vertical, compact ? 7 : 9)
                        .background(selection == meal ? Theme.primary : Color.clear, in: Capsule())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(4)
        .background(Theme.primarySoft.opacity(0.6), in: Capsule())
    }
}

struct EmptyStateView: View {
    let symbol: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 34, weight: .light))
                .foregroundStyle(Theme.primary.opacity(0.65))
            Text(title)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text(message)
                .font(.system(size: 13))
                .multilineTextAlignment(.center)
                .foregroundStyle(Theme.muted)
                .frame(maxWidth: 260)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 34)
    }
}
