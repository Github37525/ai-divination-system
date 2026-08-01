import AVFoundation

@MainActor
final class SoundEngine {
    private var players: [String: AVAudioPlayer] = [:]

    init() {
        for name in ["coin_1", "coin_2", "coin_3", "line_lock", "moving_line", "cast_complete"] {
            guard let url = Bundle.main.url(forResource: name, withExtension: "wav"),
                  let player = try? AVAudioPlayer(contentsOf: url)
            else { continue }
            player.prepareToPlay()
            players[name] = player
        }
    }

    func play(_ name: String, enabled: Bool) {
        guard enabled, let player = players[name] else { return }
        try? AVAudioSession.sharedInstance().setCategory(.ambient, options: [.mixWithOthers])
        try? AVAudioSession.sharedInstance().setActive(true)
        player.currentTime = 0
        player.play()
    }
}
