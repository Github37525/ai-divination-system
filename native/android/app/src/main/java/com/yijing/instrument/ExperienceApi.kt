package com.yijing.instrument

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class ExperienceApi(
    private val baseUrl: String = BuildConfig.EXPERIENCE_API_BASE_URL.trimEnd('/'),
) {
    suspend fun createSession(question: String): CreatedSession = withContext(Dispatchers.IO) {
        val json = request(
            path = "/v1/cast-sessions",
            method = "POST",
            body = JSONObject().put("question", question),
        )
        CreatedSession(json.toSessionSnapshot(), json.getString("session_token"))
    }

    suspend fun getSession(id: String, token: String): SessionSnapshot = withContext(Dispatchers.IO) {
        request("/v1/cast-sessions/$id", token = token).toSessionSnapshot()
    }

    suspend fun lockNextLine(
        id: String,
        token: String,
        idempotencyKey: String,
        energy: Double,
        triggerMode: String,
    ): LockedLineResponse = withContext(Dispatchers.IO) {
        val json = request(
            path = "/v1/cast-sessions/$id/lines",
            method = "POST",
            token = token,
            headers = mapOf("Idempotency-Key" to idempotencyKey),
            body = JSONObject()
                .put("motion_energy", energy.coerceIn(0.0, 100.0))
                .put("trigger_mode", triggerMode),
        )
        LockedLineResponse(
            status = json.getString("status"),
            lineCount = json.getInt("line_count"),
            line = CastLine.fromJson(json.getJSONObject("line")),
        )
    }

    suspend fun complete(id: String, token: String): CompletionResponse = withContext(Dispatchers.IO) {
        request("/v1/cast-sessions/$id/complete", method = "POST", token = token).toCompletion()
    }

    suspend fun result(id: String, token: String): CompletionResponse = withContext(Dispatchers.IO) {
        request("/v1/cast-sessions/$id/result", token = token).toCompletion()
    }

    private fun request(
        path: String,
        method: String = "GET",
        token: String? = null,
        headers: Map<String, String> = emptyMap(),
        body: JSONObject? = null,
    ): JSONObject {
        val connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 12_000
            readTimeout = 25_000
            setRequestProperty("Accept", "application/json")
            token?.let { setRequestProperty("Authorization", "Bearer $it") }
            headers.forEach(::setRequestProperty)
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body.toString()) }
            }
        }
        try {
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) {
                val message = runCatching { JSONObject(text).optString("detail") }.getOrNull()
                    .takeUnless { it.isNullOrBlank() }
                    ?: "服务暂时不可用（$status）。"
                throw ExperienceApiException(status, message)
            }
            return JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }
}

class ExperienceApiException(val status: Int, message: String) : Exception(message)
