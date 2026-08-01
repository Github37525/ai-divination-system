package com.yijing.instrument

import org.json.JSONArray
import org.json.JSONObject

data class CastLine(
    val lineIndex: Int,
    val positionName: String,
    val fronts: Int,
    val reverses: Int,
    val value: Int,
    val lineType: String,
    val moving: Boolean,
    val triggerMode: String,
    val motionEnergy: Double?,
) {
    val isYang: Boolean get() = value == 7 || value == 9

    companion object {
        fun fromJson(json: JSONObject) = CastLine(
            lineIndex = json.getInt("line_index"),
            positionName = json.getString("position_name"),
            fronts = json.getInt("fronts"),
            reverses = json.getInt("reverses"),
            value = json.getInt("value"),
            lineType = json.getString("line_type"),
            moving = json.getBoolean("moving"),
            triggerMode = json.getString("trigger_mode"),
            motionEnergy = if (json.isNull("motion_energy")) null else json.getDouble("motion_energy"),
        )
    }
}

data class SessionSnapshot(
    val sessionId: String,
    val runId: String,
    val question: String,
    val status: String,
    val lines: List<CastLine>,
)

data class CreatedSession(
    val snapshot: SessionSnapshot,
    val token: String,
)

data class LockedLineResponse(
    val status: String,
    val lineCount: Int,
    val line: CastLine,
)

data class ResultSummary(
    val hexagramName: String?,
    val changedHexagramName: String?,
    val movingLines: List<Int>,
    val interpretationStatus: String?,
    val interpretationMode: String?,
    val aiGenerated: Boolean,
    val model: String?,
    val interpretation: String?,
)

data class CompletionResponse(
    val sessionId: String,
    val runId: String,
    val status: String,
    val algorithmVersion: String,
    val lines: List<CastLine>,
    val summary: ResultSummary,
)

enum class CastFlowState(val label: String) {
    Preparing("准备"),
    Calibrating("校准中"),
    Ready("已就绪"),
    Sensing("感应动作"),
    ResultLocked("结果已锁定"),
    Animating("铜钱落定中"),
    LineComplete("一爻完成"),
    Completing("盘面生成中"),
    CastComplete("六爻完成"),
}

internal fun JSONObject.toSessionSnapshot() = SessionSnapshot(
    sessionId = getString("session_id"),
    runId = getString("run_id"),
    question = getString("question"),
    status = getString("status"),
    lines = getJSONArray("lines").toCastLines(),
)

internal fun JSONObject.toCompletion() = CompletionResponse(
    sessionId = getString("session_id"),
    runId = getString("run_id"),
    status = getString("status"),
    algorithmVersion = getString("algorithm_version"),
    lines = getJSONArray("lines").toCastLines(),
    summary = getJSONObject("result_summary").let { summary ->
        ResultSummary(
            hexagramName = summary.optionalString("hexagram_name"),
            changedHexagramName = summary.optionalString("changed_hexagram_name"),
            movingLines = summary.optJSONArray("moving_lines").toIntList(),
            interpretationStatus = summary.optionalString("interpretation_status"),
            interpretationMode = summary.optionalString("interpretation_mode"),
            aiGenerated = summary.optBoolean("ai_generated", false),
            model = summary.optionalString("model"),
            interpretation = summary.optionalString("interpretation"),
        )
    },
)

private fun JSONArray.toCastLines(): List<CastLine> =
    (0 until length()).map { CastLine.fromJson(getJSONObject(it)) }

private fun JSONArray?.toIntList(): List<Int> =
    if (this == null) emptyList() else (0 until length()).map { getInt(it) }

private fun JSONObject.optionalString(name: String): String? =
    if (isNull(name)) null else optString(name).takeUnless { it.isBlank() || it == "null" }
