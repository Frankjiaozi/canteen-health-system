import SwiftUI
import UIKit

enum Theme {
    static let background = Color(hex: 0xF7F3EC)
    static let card = Color.white
    static let ink = Color(hex: 0x1F2A26)
    static let muted = Color(hex: 0x6E7B75)
    static let primary = Color(hex: 0x24574A)
    static let primarySoft = Color(hex: 0xDDE9E2)
    static let accent = Color(hex: 0xE4693B)
    static let accentSoft = Color(hex: 0xFBE7DC)
    static let gold = Color(hex: 0xC08A3E)
    static let line = Color(hex: 0xE8E0D4)
    static let sage = Color(hex: 0x93AD9E)

    static let cardRadius: CGFloat = 22
    static let pagePadding: CGFloat = 20
}

extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: alpha
        )
    }
}

extension Font {
    static func traySerif(_ size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        .system(size: size, weight: weight, design: .serif)
    }

    static func trayNumber(_ size: CGFloat, weight: Font.Weight = .bold) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }
}

struct CardBackground: ViewModifier {
    var padding: CGFloat = 18
    var radius: CGFloat = Theme.cardRadius

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .shadow(color: Color.black.opacity(0.045), radius: 18, x: 0, y: 8)
    }
}

extension View {
    func trayCard(padding: CGFloat = 18, radius: CGFloat = Theme.cardRadius) -> some View {
        modifier(CardBackground(padding: padding, radius: radius))
    }

    func pageBackground() -> some View {
        background(Theme.background.ignoresSafeArea())
    }
}

struct PressableButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    var color: Color = Theme.primary

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 15)
            .background(color.opacity(configuration.isPressed ? 0.85 : 1), in: Capsule())
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
            .animation(.easeOut(duration: 0.16), value: configuration.isPressed)
    }
}
