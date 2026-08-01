import SwiftUI

@main
struct DivinationInstrumentApp: App {
    @StateObject private var model = CastViewModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView(model: model)
                .preferredColorScheme(.dark)
                .task { await model.restoreSession() }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active {
                model.motion.stop()
            }
        }
    }
}
