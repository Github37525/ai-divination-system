import CoreHaptics
import UIKit

@MainActor
final class HapticEngine {
    private var engine: CHHapticEngine?
    private let supportsHaptics = CHHapticEngine.capabilitiesForHardware().supportsHaptics

    init() {
        prepare()
    }

    func prepare() {
        guard supportsHaptics else { return }
        do {
            let engine = try CHHapticEngine()
            engine.isAutoShutdownEnabled = true
            engine.stoppedHandler = { _ in }
            engine.resetHandler = { try? engine.start() }
            try engine.start()
            self.engine = engine
        } catch {
            engine = nil
        }
    }

    func validMotion(enabled: Bool) {
        guard enabled else { return }
        play(intensity: 0.18, sharpness: 0.45)
    }

    func coinImpact(index: Int, enabled: Bool) {
        guard enabled else { return }
        play(intensity: 0.28 + Float(index) * 0.07, sharpness: 0.72)
    }

    func lineLocked(moving: Bool, enabled: Bool) {
        guard enabled else { return }
        if supportsHaptics {
            var events = [
                event(at: 0.00, intensity: 0.35, sharpness: 0.55),
                event(at: 0.09, intensity: 0.40, sharpness: 0.40),
            ]
            if moving {
                events.append(event(at: 0.24, intensity: 0.82, sharpness: 0.28))
            }
            play(events: events)
        } else {
            UINotificationFeedbackGenerator().notificationOccurred(moving ? .warning : .success)
        }
    }

    func castComplete(enabled: Bool) {
        guard enabled else { return }
        if supportsHaptics {
            play(events: [
                event(at: 0.00, intensity: 0.35, sharpness: 0.48),
                event(at: 0.12, intensity: 0.52, sharpness: 0.52),
                event(at: 0.26, intensity: 0.72, sharpness: 0.34),
            ])
        } else {
            UINotificationFeedbackGenerator().notificationOccurred(.success)
        }
    }

    private func play(intensity: Float, sharpness: Float) {
        guard supportsHaptics else {
            UIImpactFeedbackGenerator(style: .light).impactOccurred(intensity: CGFloat(intensity))
            return
        }
        play(events: [event(at: 0, intensity: intensity, sharpness: sharpness)])
    }

    private func event(at time: TimeInterval, intensity: Float, sharpness: Float) -> CHHapticEvent {
        CHHapticEvent(
            eventType: .hapticTransient,
            parameters: [
                CHHapticEventParameter(parameterID: .hapticIntensity, value: intensity),
                CHHapticEventParameter(parameterID: .hapticSharpness, value: sharpness),
            ],
            relativeTime: time
        )
    }

    private func play(events: [CHHapticEvent]) {
        guard let engine else { return }
        do {
            try engine.start()
            let pattern = try CHHapticPattern(events: events, parameters: [])
            try engine.makePlayer(with: pattern).start(atTime: 0)
        } catch {
            self.engine = nil
            prepare()
        }
    }
}
