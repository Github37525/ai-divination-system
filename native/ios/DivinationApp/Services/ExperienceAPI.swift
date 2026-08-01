import Foundation

enum ExperienceAPIError: LocalizedError {
    case invalidResponse
    case server(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "服务响应格式异常，请稍后重试。"
        case let .server(_, message):
            return message
        }
    }
}

actor ExperienceAPI {
    static let shared = ExperienceAPI()

    private let baseURL: URL
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init() {
        let configured = ProcessInfo.processInfo.environment["EXPERIENCE_API_BASE_URL"]
        baseURL = URL(string: configured ?? "https://ai-divination-experience.onrender.com")!
    }

    func createSession(question: String) async throws -> CreatedSession {
        try await request(
            path: "/v1/cast-sessions",
            method: "POST",
            body: ["question": question]
        )
    }

    func getSession(id: String, token: String) async throws -> SessionSnapshot {
        try await request(path: "/v1/cast-sessions/\(id)", token: token)
    }

    func lockNextLine(
        id: String,
        token: String,
        idempotencyKey: String,
        energy: Double,
        triggerMode: String
    ) async throws -> LockedLineResponse {
        try await request(
            path: "/v1/cast-sessions/\(id)/lines",
            method: "POST",
            token: token,
            headers: ["Idempotency-Key": idempotencyKey],
            body: ["motion_energy": energy, "trigger_mode": triggerMode]
        )
    }

    func complete(id: String, token: String) async throws -> CompletionResponse {
        try await request(
            path: "/v1/cast-sessions/\(id)/complete",
            method: "POST",
            token: token
        )
    }

    func result(id: String, token: String) async throws -> CompletionResponse {
        try await request(path: "/v1/cast-sessions/\(id)/result", token: token)
    }

    private func request<Response: Decodable>(
        path: String,
        method: String = "GET",
        token: String? = nil,
        headers: [String: String] = [:],
        body: [String: Any]? = nil
    ) async throws -> Response {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = method
        request.timeoutInterval = 25
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        for (name, value) in headers {
            request.setValue(value, forHTTPHeaderField: name)
        }
        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw ExperienceAPIError.invalidResponse
        }
        guard 200..<300 ~= http.statusCode else {
            let payload = try? decoder.decode(APIErrorPayload.self, from: data)
            throw ExperienceAPIError.server(
                http.statusCode,
                payload?.detail ?? "服务暂时不可用（\(http.statusCode)）。"
            )
        }
        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw ExperienceAPIError.invalidResponse
        }
    }
}

private struct APIErrorPayload: Decodable {
    let detail: String
}
