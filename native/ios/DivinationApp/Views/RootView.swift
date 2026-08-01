import SwiftUI

struct RootView: View {
    @ObservedObject var model: CastViewModel

    var body: some View {
        ZStack {
            StarfieldBackground()
            Group {
                if let completion = model.completion {
                    ResultView(model: model, completion: completion)
                } else if model.snapshot != nil {
                    CastScreen(model: model, motion: model.motion)
                } else {
                    QuestionView(model: model)
                }
            }
        }
        .tint(AstronomyTheme.bronze)
        .alert("未能完成", isPresented: Binding(
            get: { model.errorMessage != nil },
            set: { if !$0 { model.errorMessage = nil } }
        )) {
            Button("知道了", role: .cancel) { model.errorMessage = nil }
        } message: {
            Text(model.errorMessage ?? "请稍后重试。")
        }
    }
}

private struct QuestionView: View {
    @ObservedObject var model: CastViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Spacer(minLength: 34)
                VStack(alignment: .leading, spacing: 8) {
                    Text("天文铜仪")
                        .font(.system(size: 40, weight: .semibold, design: .serif))
                        .foregroundStyle(AstronomyTheme.paleBronze)
                    Text("以手机动作触发 · 以服务端规则锁定")
                        .font(.subheadline)
                        .foregroundStyle(AstronomyTheme.paper.opacity(0.66))
                }

                VStack(alignment: .leading, spacing: 14) {
                    Label("你此刻想理清什么？", systemImage: "scope")
                        .font(.headline)
                    TextEditor(text: $model.question)
                        .frame(minHeight: 120)
                        .scrollContentBackground(.hidden)
                        .padding(12)
                        .background(AstronomyTheme.ink.opacity(0.55), in: RoundedRectangle(cornerRadius: 16))
                        .accessibilityLabel("问题")

                    Button {
                        Task { await model.startSession() }
                    } label: {
                        HStack {
                            if model.isBusy { ProgressView().tint(AstronomyTheme.ink) }
                            Text(model.isBusy ? "正在建立会话" : "填写完成，开始摇卦")
                            Spacer()
                            Image(systemName: "arrow.right")
                        }
                        .fontWeight(.semibold)
                        .padding(.horizontal, 18)
                        .frame(height: 54)
                        .foregroundStyle(AstronomyTheme.ink)
                        .background(AstronomyTheme.paleBronze, in: RoundedRectangle(cornerRadius: 17))
                    }
                    .disabled(!model.canStart)
                    .opacity(model.canStart ? 1 : 0.46)
                }
                .instrumentPanel()

                VStack(alignment: .leading, spacing: 9) {
                    Label("京房纳甲六爻", systemImage: "seal")
                    Label("真太阳时与历法规则由服务端统一计算", systemImage: "clock")
                    Label("AI 不参与排盘，只解释已经锁定的结果", systemImage: "checkmark.shield")
                }
                .font(.footnote)
                .foregroundStyle(AstronomyTheme.paper.opacity(0.72))
                .padding(.horizontal, 4)
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 30)
        }
    }
}

private struct CastScreen: View {
    @ObservedObject var model: CastViewModel
    @ObservedObject var motion: MotionShakeDetector

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                header
                CoinStageView(model: model)
                    .instrumentPanel()
                LineProgressView(lines: model.lines, pending: model.pendingLine)
                    .instrumentPanel()
                controls
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 18)
        }
        .onAppear {
            motion.start()
            model.updateCalibrationState()
        }
        .onDisappear { motion.stop() }
        .onChange(of: motion.isReady) { _, _ in model.updateCalibrationState() }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 5) {
                Text(model.flowState.rawValue)
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(AstronomyTheme.paleBronze)
                Text(statusDetail)
                    .font(.footnote)
                    .foregroundStyle(AstronomyTheme.paper.opacity(0.62))
            }
            Spacer()
            Text("\(model.lines.count + (model.pendingLine == nil ? 0 : 1))/6")
                .font(.system(.title3, design: .monospaced, weight: .semibold))
                .foregroundStyle(AstronomyTheme.jade)
                .padding(.horizontal, 12)
                .padding(.vertical, 7)
                .background(AstronomyTheme.jade.opacity(0.1), in: Capsule())
        }
    }

    private var statusDetail: String {
        if !motion.isAvailable { return "本机无可用动作传感器，请使用点按起爻。" }
        if !motion.isReady { return "请平稳握持片刻 · \(Int(motion.calibrationProgress * 100))%" }
        if model.pendingLine != nil { return "结果已先锁定，正在呈现三枚铜钱。" }
        return "自然摇动手机三次，或使用点按起爻。"
    }

    private var controls: some View {
        VStack(spacing: 12) {
            Button(action: model.tapFallback) {
                Label("点按起第 \(min(model.lines.count + 1, 6)) 爻", systemImage: "hand.tap")
                    .frame(maxWidth: .infinity)
                    .frame(height: 50)
                    .fontWeight(.semibold)
                    .foregroundStyle(AstronomyTheme.ink)
                    .background(AstronomyTheme.paleBronze, in: RoundedRectangle(cornerRadius: 16))
            }
            .disabled(!model.canTrigger)
            .opacity(model.canTrigger ? 1 : 0.42)

            HStack(spacing: 16) {
                Toggle(isOn: $model.soundEnabled) {
                    Label("音效", systemImage: model.soundEnabled ? "speaker.wave.2" : "speaker.slash")
                }
                Toggle(isOn: $model.hapticsEnabled) {
                    Label("触觉", systemImage: "waveform.path")
                }
            }
            .toggleStyle(.switch)
            .font(.footnote)
            .foregroundStyle(AstronomyTheme.paper.opacity(0.75))
        }
    }
}

private struct ResultView: View {
    @ObservedObject var model: CastViewModel
    let completion: CompletionResponse

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Spacer(minLength: 20)
                Text("盘面已锁定")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AstronomyTheme.jade)
                Text(title)
                    .font(.system(size: 34, weight: .semibold, design: .serif))
                    .foregroundStyle(AstronomyTheme.paleBronze)

                LineProgressView(lines: completion.lines, pending: nil)
                    .instrumentPanel()

                VStack(alignment: .leading, spacing: 12) {
                    Label(interpretationStage, systemImage: stageIcon)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(AstronomyTheme.jade)
                    Text(completion.resultSummary.interpretation ?? "确定性盘面已可查看，DeepSeek 正在后台生成白话解读。")
                        .font(.body)
                        .foregroundStyle(AstronomyTheme.paper.opacity(0.9))
                        .textSelection(.enabled)
                }
                .instrumentPanel()

                VStack(alignment: .leading, spacing: 7) {
                    Text("可核验信息")
                        .font(.headline)
                    Text("算法 \(completion.algorithmVersion) · Run ID \(completion.runId.prefix(8))")
                    Text("动爻：\(movingLineText)")
                    Text("AI 只解释已锁定盘面，不改变卦象。")
                }
                .font(.footnote)
                .foregroundStyle(AstronomyTheme.paper.opacity(0.62))
                .instrumentPanel()

                Button("完成并开始新的问题", action: model.reset)
                    .frame(maxWidth: .infinity)
                    .frame(height: 50)
                    .buttonStyle(.bordered)
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 30)
        }
    }

    private var title: String {
        guard let changed = completion.resultSummary.changedHexagramName, !changed.isEmpty else {
            return completion.resultSummary.hexagramName ?? "六爻完成"
        }
        return "\(completion.resultSummary.hexagramName ?? "本卦") → \(changed)"
    }

    private var interpretationStage: String {
        switch completion.status {
        case "interpretation_pending", "interpreting": return "生成白话解读 · 可稍后回来"
        case "interpretation_failed": return "解读暂未完成 · 盘面已保留"
        default: return completion.resultSummary.aiGenerated ? "DeepSeek 解读完成" : "规则解读完成"
        }
    }

    private var stageIcon: String {
        completion.status == "completed" ? "checkmark.circle" : "hourglass"
    }

    private var movingLineText: String {
        let lines = completion.lines.filter(\.moving).map(\.positionName)
        return lines.isEmpty ? "无" : lines.joined(separator: "、")
    }
}
