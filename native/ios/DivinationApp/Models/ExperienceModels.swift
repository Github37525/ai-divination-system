import Foundation

struct CastLine: Codable, Identifiable, Equatable {
    let lineIndex: Int
    let positionName: String
    let fronts: Int
    let reverses: Int
    let value: Int
    let lineType: String
    let moving: Bool
    let triggerMode: String
    let motionEnergy: Double?

    var id: Int { lineIndex }
    var isYang: Bool { value == 7 || value == 9 }

    enum CodingKeys: String, CodingKey {
        case lineIndex = "line_index"
        case positionName = "position_name"
        case fronts, reverses, value
        case lineType = "line_type"
        case moving
        case triggerMode = "trigger_mode"
        case motionEnergy = "motion_energy"
    }
}

struct SessionSnapshot: Codable {
    let sessionId: String
    let runId: String
    let question: String
    let status: String
    let lineCount: Int
    let lines: [CastLine]
    let seedCommitment: String
    let algorithmVersion: String
    let createdAt: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case runId = "run_id"
        case question, status
        case lineCount = "line_count"
        case lines
        case seedCommitment = "seed_commitment"
        case algorithmVersion = "algorithm_version"
        case createdAt = "created_at"
        case expiresAt = "expires_at"
    }
}

struct CreatedSession: Codable {
    let sessionId: String
    let runId: String
    let question: String
    let status: String
    let lineCount: Int
    let lines: [CastLine]
    let seedCommitment: String
    let algorithmVersion: String
    let createdAt: String
    let expiresAt: String
    let sessionToken: String

    var snapshot: SessionSnapshot {
        SessionSnapshot(
            sessionId: sessionId,
            runId: runId,
            question: question,
            status: status,
            lineCount: lineCount,
            lines: lines,
            seedCommitment: seedCommitment,
            algorithmVersion: algorithmVersion,
            createdAt: createdAt,
            expiresAt: expiresAt
        )
    }

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case runId = "run_id"
        case question, status
        case lineCount = "line_count"
        case lines
        case seedCommitment = "seed_commitment"
        case algorithmVersion = "algorithm_version"
        case createdAt = "created_at"
        case expiresAt = "expires_at"
        case sessionToken = "session_token"
    }
}

struct LockedLineResponse: Decodable {
    let sessionId: String
    let runId: String
    let status: String
    let lineCount: Int
    let line: CastLine

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case runId = "run_id"
        case status
        case lineCount = "line_count"
        case line
    }
}

struct ResultSummary: Codable {
    let hexagramName: String?
    let changedHexagramName: String?
    let movingLines: [Int]
    let interpretationStatus: String?
    let interpretationMode: String?
    let aiGenerated: Bool
    let model: String?
    let interpretation: String?

    enum CodingKeys: String, CodingKey {
        case hexagramName = "hexagram_name"
        case changedHexagramName = "changed_hexagram_name"
        case movingLines = "moving_lines"
        case interpretationStatus = "interpretation_status"
        case interpretationMode = "interpretation_mode"
        case aiGenerated = "ai_generated"
        case model, interpretation
    }
}

struct CompletionResponse: Codable {
    let sessionId: String
    let runId: String
    let status: String
    let seedCommitment: String
    let seedReveal: String
    let algorithmVersion: String
    let lines: [CastLine]
    let resultSummary: ResultSummary

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case runId = "run_id"
        case status
        case seedCommitment = "seed_commitment"
        case seedReveal = "seed_reveal"
        case algorithmVersion = "algorithm_version"
        case lines
        case resultSummary = "result_summary"
    }
}

enum CastFlowState: String {
    case preparing = "准备"
    case calibrating = "校准中"
    case ready = "已就绪"
    case sensing = "感应动作"
    case resultLocked = "结果已锁定"
    case animating = "铜钱落定中"
    case lineComplete = "一爻完成"
    case completing = "盘面生成中"
    case castComplete = "六爻完成"
}
