import SwiftUI

private enum CoinPhase {
    case resting, rising, apex, impact, settled
}

struct CoinStageView: View {
    @ObservedObject var model: CastViewModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var phase: CoinPhase = .resting

    var body: some View {
        VStack(spacing: 16) {
            ZStack {
                Circle()
                    .stroke(AstronomyTheme.bronze.opacity(0.16), lineWidth: 1)
                    .frame(width: 260, height: 260)
                Circle()
                    .trim(from: 0, to: max(0.05, model.motion.energy / 100))
                    .stroke(AstronomyTheme.jade, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .frame(width: 238, height: 238)
                    .animation(.easeOut(duration: 0.12), value: model.motion.energy)

                HStack(spacing: -6) {
                    ForEach(0..<3, id: \.self) { index in
                        CoinView(
                            index: index,
                            phase: phase,
                            isFront: isFront(index),
                            showFace: phase == .settled
                        )
                    }
                }
            }
            .frame(height: 274)

            Text(model.pendingLine.map { "\($0.fronts) 正 · \($0.reverses) 反 · \($0.lineType)" } ?? "动作能量 \(Int(model.motion.energy))")
                .font(.system(.subheadline, design: .monospaced, weight: .medium))
                .foregroundStyle(model.pendingLine == nil ? AstronomyTheme.paper.opacity(0.55) : AstronomyTheme.paleBronze)
                .contentTransition(.numericText())
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(model.pendingLine.map { "\($0.fronts)正\($0.reverses)反，\($0.lineType)" } ?? "等待摇动手机")
        .onChange(of: model.animationToken) { _, _ in
            guard model.pendingLine != nil else { return }
            Task { await playAnimation() }
        }
    }

    private func isFront(_ index: Int) -> Bool {
        guard let pending = model.pendingLine else { return true }
        return index < pending.fronts
    }

    @MainActor
    private func playAnimation() async {
        if reduceMotion {
            withAnimation(.easeOut(duration: 0.18)) { phase = .settled }
            try? await Task.sleep(for: .milliseconds(360))
            model.animationCompleted()
            return
        }
        phase = .resting
        withAnimation(.spring(response: 0.34, dampingFraction: 0.70)) { phase = .rising }
        try? await Task.sleep(for: .milliseconds(260))
        withAnimation(.easeOut(duration: 0.22)) { phase = .apex }
        try? await Task.sleep(for: .milliseconds(230))
        withAnimation(.easeIn(duration: 0.36)) { phase = .impact }
        try? await Task.sleep(for: .milliseconds(390))
        withAnimation(.spring(response: 0.42, dampingFraction: 0.62)) { phase = .settled }
        try? await Task.sleep(for: .milliseconds(500))
        model.animationCompleted()
    }
}

private struct CoinView: View {
    let index: Int
    let phase: CoinPhase
    let isFront: Bool
    let showFace: Bool

    var body: some View {
        ZStack {
            Image("bronze_coin")
                .resizable()
                .scaledToFit()
            if showFace {
                Text(isFront ? "正" : "反")
                    .font(.system(size: 13, weight: .bold, design: .serif))
                    .foregroundStyle(Color.black.opacity(0.68))
                    .padding(6)
                    .background(AstronomyTheme.paleBronze.opacity(0.72), in: Circle())
            }
        }
        .frame(width: 96, height: 96)
        .shadow(color: .black.opacity(0.48), radius: phase == .settled ? 8 : 18, y: phase == .settled ? 8 : 20)
        .offset(x: xOffset, y: yOffset)
        .rotationEffect(.degrees(zRotation))
        .rotation3DEffect(.degrees(xRotation), axis: (x: 1, y: 0.12, z: 0))
        .zIndex(Double(3 - index))
    }

    private var xOffset: CGFloat {
        switch phase {
        case .resting: return CGFloat(index - 1) * 2
        case .rising, .apex: return CGFloat(index - 1) * 18
        case .impact: return CGFloat(index - 1) * 11
        case .settled: return CGFloat(index - 1) * 8
        }
    }

    private var yOffset: CGFloat {
        switch phase {
        case .resting: return 46
        case .rising: return -54 - CGFloat(index * 7)
        case .apex: return -76 - CGFloat((2 - index) * 8)
        case .impact: return 30 + CGFloat(index * 4)
        case .settled: return 18 + CGFloat(index * 3)
        }
    }

    private var xRotation: Double {
        switch phase {
        case .resting: return 0
        case .rising: return 220 + Double(index * 44)
        case .apex: return 510 + Double(index * 72)
        case .impact: return 790 + Double(index * 54)
        case .settled: return isFront ? 720 : 900
        }
    }

    private var zRotation: Double {
        switch phase {
        case .resting: return Double(index - 1) * 7
        case .rising: return Double(index - 1) * 22
        case .apex: return Double(index - 1) * 34
        case .impact: return Double(index - 1) * 13
        case .settled: return Double(index - 1) * 9
        }
    }
}

struct LineProgressView: View {
    let lines: [CastLine]
    let pending: CastLine?

    var body: some View {
        VStack(spacing: 12) {
            ForEach((1...6).reversed(), id: \.self) { index in
                let line = line(at: index)
                HStack(spacing: 12) {
                    Text(positionName(index))
                        .font(.caption)
                        .foregroundStyle(AstronomyTheme.paper.opacity(0.48))
                        .frame(width: 34, alignment: .leading)
                    LineGlyph(line: line)
                    Text(line?.lineType ?? "待开始")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(line == nil ? AstronomyTheme.paper.opacity(0.28) : line!.moving ? AstronomyTheme.jade : AstronomyTheme.paper)
                        .frame(width: 48, alignment: .trailing)
                }
            }
        }
        .accessibilityElement(children: .contain)
    }

    private func line(at index: Int) -> CastLine? {
        pending?.lineIndex == index ? pending : lines.first { $0.lineIndex == index }
    }

    private func positionName(_ index: Int) -> String {
        ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"][index - 1]
    }
}

private struct LineGlyph: View {
    let line: CastLine?

    var body: some View {
        HStack(spacing: line?.isYang == true ? 0 : 13) {
            Capsule().frame(maxWidth: .infinity)
            if line?.isYang != true { Capsule().frame(maxWidth: .infinity) }
        }
        .frame(height: 7)
        .foregroundStyle(line == nil ? AstronomyTheme.paper.opacity(0.12) : line!.moving ? AstronomyTheme.jade : AstronomyTheme.paleBronze)
        .animation(.spring(response: 0.45, dampingFraction: 0.74), value: line)
    }
}
