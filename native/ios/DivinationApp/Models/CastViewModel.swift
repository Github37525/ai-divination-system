import SwiftUI

@MainActor
final class CastViewModel: ObservableObject {
    @Published var question = ""
    @Published private(set) var snapshot: SessionSnapshot?
    @Published private(set) var lines: [CastLine] = []
    @Published private(set) var pendingLine: CastLine?
    @Published private(set) var completion: CompletionResponse?
    @Published private(set) var flowState: CastFlowState = .preparing
    @Published private(set) var isBusy = false
    @Published var errorMessage: String?
    @Published var animationToken = UUID()
    @Published var soundEnabled = UserDefaults.standard.bool(forKey: "soundEnabled") {
        didSet { UserDefaults.standard.set(soundEnabled, forKey: "soundEnabled") }
    }
    @Published var hapticsEnabled = UserDefaults.standard.object(forKey: "hapticsEnabled") as? Bool ?? true {
        didSet { UserDefaults.standard.set(hapticsEnabled, forKey: "hapticsEnabled") }
    }

    let motion = MotionShakeDetector()

    private let api = ExperienceAPI.shared
    private let vault = SessionVault()
    private let haptics = HapticEngine()
    private let sound = SoundEngine()
    private var token: String?
    private var pollingTask: Task<Void, Never>?

    init() {
        motion.onShake = { [weak self] energy in
            self?.triggerLine(energy: energy, mode: "motion")
        }
    }

    var canStart: Bool {
        !question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isBusy
    }

    var canTrigger: Bool {
        snapshot != nil && pendingLine == nil && lines.count < 6 && !isBusy
            && (flowState == .ready || flowState == .lineComplete)
    }

    func startSession() async {
        let trimmed = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isBusy = true
        errorMessage = nil
        do {
            let created = try await api.createSession(question: trimmed)
            snapshot = created.snapshot
            lines = created.lines
            token = created.sessionToken
            vault.save(id: created.sessionId, token: created.sessionToken)
            flowState = .calibrating
            motion.start()
        } catch {
            errorMessage = error.localizedDescription
        }
        isBusy = false
    }

    func restoreSession() async {
        guard snapshot == nil, let stored = vault.load() else { return }
        isBusy = true
        do {
            let restored = try await api.getSession(id: stored.id, token: stored.token)
            snapshot = restored
            question = restored.question
            lines = restored.lines
            token = stored.token
            if restored.lineCount >= 6 {
                await fetchOrComplete(status: restored.status)
            } else {
                flowState = .calibrating
                motion.start()
            }
        } catch {
            vault.clear()
            errorMessage = "未能恢复上次会话，您可以重新开始。"
        }
        isBusy = false
    }

    func updateCalibrationState() {
        guard snapshot != nil, pendingLine == nil, lines.count < 6 else { return }
        flowState = motion.isReady ? .ready : .calibrating
    }

    func triggerLine(energy: Double, mode: String) {
        guard canTrigger else { return }
        flowState = .sensing
        haptics.validMotion(enabled: hapticsEnabled)
        isBusy = true
        Task { await lockNextLine(energy: energy, mode: mode) }
    }

    func tapFallback() {
        triggerLine(energy: max(18, motion.energy), mode: "tap")
    }

    func animationCompleted() {
        guard let pendingLine else { return }
        if !lines.contains(where: { $0.id == pendingLine.id }) {
            lines.append(pendingLine)
            lines.sort { $0.lineIndex < $1.lineIndex }
        }
        self.pendingLine = nil
        if lines.count == 6 {
            Task { await completeCast() }
        } else {
            flowState = .lineComplete
            Task {
                try? await Task.sleep(for: .milliseconds(320))
                if self.pendingLine == nil { self.flowState = .ready }
            }
        }
    }

    func reset() {
        pollingTask?.cancel()
        motion.stop()
        vault.clear()
        snapshot = nil
        token = nil
        lines = []
        pendingLine = nil
        completion = nil
        question = ""
        errorMessage = nil
        flowState = .preparing
    }

    private func lockNextLine(energy: Double, mode: String) async {
        guard let snapshot, let token else { return }
        let key = "native-\(snapshot.sessionId)-\(lines.count + 1)-\(UUID().uuidString)"
        do {
            let locked = try await api.lockNextLine(
                id: snapshot.sessionId,
                token: token,
                idempotencyKey: key,
                energy: min(100, max(0, energy)),
                triggerMode: mode
            )
            flowState = .resultLocked
            pendingLine = locked.line
            animationToken = UUID()
            flowState = .animating
            playLockedFeedback(for: locked.line)
        } catch {
            errorMessage = error.localizedDescription
            flowState = .ready
        }
        isBusy = false
    }

    private func playLockedFeedback(for line: CastLine) {
        let reducedMotion = UIAccessibility.isReduceMotionEnabled
        Task {
            let delays = reducedMotion ? [80, 150, 220] : [560, 760, 960]
            for index in 0..<3 {
                try? await Task.sleep(for: .milliseconds(delays[index] - (index == 0 ? 0 : delays[index - 1])))
                haptics.coinImpact(index: index, enabled: hapticsEnabled)
                sound.play("coin_\(index + 1)", enabled: soundEnabled)
            }
            try? await Task.sleep(for: .milliseconds(reducedMotion ? 90 : 220))
            haptics.lineLocked(moving: line.moving, enabled: hapticsEnabled)
            sound.play(line.moving ? "moving_line" : "line_lock", enabled: soundEnabled)
        }
    }

    private func completeCast() async {
        guard let snapshot, let token else { return }
        motion.stop()
        flowState = .completing
        isBusy = true
        do {
            let response = try await api.complete(id: snapshot.sessionId, token: token)
            completion = response
            lines = response.lines
            flowState = .castComplete
            haptics.castComplete(enabled: hapticsEnabled)
            sound.play("cast_complete", enabled: soundEnabled)
            if response.status == "interpretation_pending" || response.status == "interpreting" {
                startPolling()
            } else {
                vault.clear()
            }
        } catch {
            errorMessage = error.localizedDescription
            flowState = .lineComplete
        }
        isBusy = false
    }

    private func fetchOrComplete(status: String) async {
        guard let snapshot, let token else { return }
        do {
            if status == "ready_to_complete" || status == "ready" {
                completion = try await api.complete(id: snapshot.sessionId, token: token)
            } else {
                completion = try await api.result(id: snapshot.sessionId, token: token)
            }
            if let completion {
                lines = completion.lines
                flowState = .castComplete
                if completion.status == "interpretation_pending" || completion.status == "interpreting" {
                    startPolling()
                } else {
                    vault.clear()
                }
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func startPolling() {
        pollingTask?.cancel()
        guard let snapshot, let token else { return }
        pollingTask = Task {
            for _ in 0..<24 where !Task.isCancelled {
                try? await Task.sleep(for: .seconds(2))
                guard !Task.isCancelled else { return }
                do {
                    let response = try await api.result(id: snapshot.sessionId, token: token)
                    completion = response
                    if response.status == "completed" || response.status == "interpretation_failed" {
                        vault.clear()
                        return
                    }
                } catch {
                    errorMessage = "解读仍在后台生成，稍后可重新进入查看。"
                    return
                }
            }
        }
    }
}
