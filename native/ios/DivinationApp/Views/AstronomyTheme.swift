import SwiftUI

enum AstronomyTheme {
    static let ink = Color(red: 0.025, green: 0.045, blue: 0.06)
    static let panel = Color(red: 0.055, green: 0.085, blue: 0.10)
    static let bronze = Color(red: 0.76, green: 0.56, blue: 0.27)
    static let paleBronze = Color(red: 0.92, green: 0.78, blue: 0.48)
    static let jade = Color(red: 0.30, green: 0.72, blue: 0.67)
    static let paper = Color(red: 0.88, green: 0.86, blue: 0.76)
}

struct InstrumentPanel: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(18)
            .background(
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .fill(AstronomyTheme.panel.opacity(0.92))
                    .overlay {
                        RoundedRectangle(cornerRadius: 24, style: .continuous)
                            .stroke(AstronomyTheme.bronze.opacity(0.28), lineWidth: 1)
                    }
            )
    }
}

extension View {
    func instrumentPanel() -> some View { modifier(InstrumentPanel()) }
}

struct StarfieldBackground: View {
    var body: some View {
        ZStack {
            AstronomyTheme.ink
            RadialGradient(
                colors: [AstronomyTheme.jade.opacity(0.16), .clear],
                center: .topTrailing,
                startRadius: 20,
                endRadius: 430
            )
            Canvas { context, size in
                for index in 0..<42 {
                    let x = CGFloat((index * 73) % 101) / 101 * size.width
                    let y = CGFloat((index * 47) % 97) / 97 * size.height
                    let radius = index.isMultiple(of: 7) ? 1.4 : 0.7
                    context.fill(
                        Path(ellipseIn: CGRect(x: x, y: y, width: radius, height: radius)),
                        with: .color(AstronomyTheme.paleBronze.opacity(0.28))
                    )
                }
            }
        }
        .ignoresSafeArea()
    }
}
