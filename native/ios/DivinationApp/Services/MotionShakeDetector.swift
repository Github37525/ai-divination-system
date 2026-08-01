import CoreMotion
import Foundation

@MainActor
final class MotionShakeDetector: ObservableObject {
    @Published private(set) var calibrationProgress = 0.0
    @Published private(set) var energy = 0.0
    @Published private(set) var isReady = false
    @Published private(set) var isAvailable = true

    var onShake: ((Double) -> Void)?

    private let manager = CMMotionManager()
    private let queue: OperationQueue = {
        let queue = OperationQueue()
        queue.name = "com.yijing.instrument.motion"
        queue.qualityOfService = .userInteractive
        queue.maxConcurrentOperationCount = 1
        return queue
    }()
    private var calibrationSamples = 0
    private var impulses: [TimeInterval] = []
    private var lastImpulseAt = 0.0
    private var cooldownUntil = 0.0

    func start() {
        guard !manager.isDeviceMotionActive else { return }
        guard manager.isDeviceMotionAvailable else {
            isAvailable = false
            isReady = true
            return
        }
        isAvailable = true
        calibrationSamples = 0
        calibrationProgress = 0
        isReady = false
        impulses.removeAll()
        manager.deviceMotionUpdateInterval = 1.0 / 60.0
        manager.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: queue) { [weak self] motion, _ in
            guard let self, let motion else { return }
            let acceleration = motion.userAcceleration
            let rotation = motion.rotationRate
            let accelerationMagnitude = sqrt(
                acceleration.x * acceleration.x
                    + acceleration.y * acceleration.y
                    + acceleration.z * acceleration.z
            )
            let rotationMagnitude = sqrt(
                rotation.x * rotation.x
                    + rotation.y * rotation.y
                    + rotation.z * rotation.z
            )
            Task { @MainActor in
                self.consume(
                    acceleration: accelerationMagnitude,
                    rotation: rotationMagnitude,
                    timestamp: motion.timestamp
                )
            }
        }
    }

    func stop() {
        manager.stopDeviceMotionUpdates()
        isReady = false
        energy = 0
    }

    private func consume(acceleration: Double, rotation: Double, timestamp: TimeInterval) {
        if calibrationSamples < 30 {
            calibrationSamples += 1
            calibrationProgress = Double(calibrationSamples) / 30.0
            isReady = calibrationSamples == 30
            return
        }

        energy = min(100, max(acceleration / 1.15, rotation / 2.2) * 58)
        guard timestamp >= cooldownUntil else { return }
        guard acceleration >= 1.15 || rotation >= 2.2 else { return }
        guard timestamp - lastImpulseAt >= 0.11 else { return }

        lastImpulseAt = timestamp
        impulses.append(timestamp)
        impulses.removeAll { timestamp - $0 > 0.9 }
        if impulses.count >= 3 {
            impulses.removeAll()
            cooldownUntil = timestamp + 1.8
            onShake?(energy)
        }
    }
}
