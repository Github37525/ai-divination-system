package com.yijing.instrument

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

data class CastUiState(
    val question: String = "",
    val session: SessionSnapshot? = null,
    val lines: List<CastLine> = emptyList(),
    val pendingLine: CastLine? = null,
    val completion: CompletionResponse? = null,
    val flow: CastFlowState = CastFlowState.Preparing,
    val busy: Boolean = false,
    val error: String? = null,
    val soundEnabled: Boolean = false,
    val hapticsEnabled: Boolean = true,
    val animationToken: Long = 0,
)

class CastViewModel(application: Application) : AndroidViewModel(application) {
    private val api = ExperienceApi()
    private val store = SessionStore(application)
    private val feedback = Feedback(application)
    private val preferences = application.getSharedPreferences("experience_settings", 0)
    val motion = MotionShakeDetector(application)

    private val _uiState = MutableStateFlow(
        CastUiState(
            soundEnabled = preferences.getBoolean("sound_enabled", false),
            hapticsEnabled = preferences.getBoolean("haptics_enabled", true),
        ),
    )
    val uiState: StateFlow<CastUiState> = _uiState.asStateFlow()
    private var token: String? = null

    init {
        motion.onShake = { energy -> triggerLine(energy, "motion") }
        motion.onReady = {
            _uiState.update { state ->
                if (state.session != null && state.pendingLine == null && state.lines.size < 6) {
                    state.copy(flow = CastFlowState.Ready)
                } else state
            }
        }
        restoreSession()
    }

    fun updateQuestion(value: String) {
        _uiState.update { it.copy(question = value.take(500)) }
    }

    fun startSession() {
        val question = uiState.value.question.trim()
        if (question.isEmpty() || uiState.value.busy) return
        viewModelScope.launch {
            _uiState.update { it.copy(busy = true, error = null) }
            runCatching { api.createSession(question) }
                .onSuccess { created ->
                    token = created.token
                    store.save(created.snapshot.sessionId, created.token)
                    _uiState.update {
                        it.copy(
                            session = created.snapshot,
                            lines = created.snapshot.lines,
                            flow = CastFlowState.Calibrating,
                            busy = false,
                        )
                    }
                }
                .onFailure(::showError)
        }
    }

    fun tapFallback() {
        triggerLine(uiState.value.let { motion.energy.value.coerceAtLeast(18.0) }, "tap")
    }

    fun triggerLine(energy: Double, mode: String) {
        val state = uiState.value
        if (state.session == null || state.pendingLine != null || state.lines.size >= 6 || state.busy) return
        if (state.flow != CastFlowState.Ready && state.flow != CastFlowState.LineComplete) return
        feedback.validMotion(state.hapticsEnabled)
        _uiState.update { it.copy(flow = CastFlowState.Sensing, busy = true, error = null) }
        viewModelScope.launch { lockNextLine(energy, mode) }
    }

    fun animationCompleted() {
        val pending = uiState.value.pendingLine ?: return
        val updatedLines = (uiState.value.lines + pending)
            .distinctBy { it.lineIndex }
            .sortedBy { it.lineIndex }
        _uiState.update {
            it.copy(
                lines = updatedLines,
                pendingLine = null,
                flow = if (updatedLines.size == 6) CastFlowState.Completing else CastFlowState.LineComplete,
            )
        }
        if (updatedLines.size == 6) {
            viewModelScope.launch { completeCast() }
        } else {
            viewModelScope.launch {
                delay(320)
                _uiState.update { current ->
                    if (current.pendingLine == null) current.copy(flow = CastFlowState.Ready) else current
                }
            }
        }
    }

    fun setSoundEnabled(enabled: Boolean) {
        preferences.edit().putBoolean("sound_enabled", enabled).apply()
        _uiState.update { it.copy(soundEnabled = enabled) }
    }

    fun setHapticsEnabled(enabled: Boolean) {
        preferences.edit().putBoolean("haptics_enabled", enabled).apply()
        _uiState.update { it.copy(hapticsEnabled = enabled) }
    }

    fun clearError() {
        _uiState.update { it.copy(error = null) }
    }

    fun reset() {
        motion.stop()
        store.clear()
        token = null
        _uiState.update {
            CastUiState(
                soundEnabled = it.soundEnabled,
                hapticsEnabled = it.hapticsEnabled,
            )
        }
    }

    private fun restoreSession() {
        val stored = store.load() ?: return
        viewModelScope.launch {
            _uiState.update { it.copy(busy = true) }
            runCatching { api.getSession(stored.id, stored.token) }
                .onSuccess { restored ->
                    token = stored.token
                    _uiState.update {
                        it.copy(
                            question = restored.question,
                            session = restored,
                            lines = restored.lines,
                            flow = if (restored.lines.size < 6) CastFlowState.Calibrating else CastFlowState.Completing,
                            busy = false,
                        )
                    }
                    if (restored.lines.size >= 6) fetchOrComplete(restored.status)
                }
                .onFailure {
                    store.clear()
                    _uiState.update { state ->
                        state.copy(busy = false, error = "未能恢复上次会话，您可以重新开始。")
                    }
                }
        }
    }

    private suspend fun lockNextLine(energy: Double, mode: String) {
        val session = uiState.value.session ?: return
        val activeToken = token ?: return
        val key = "native-${session.sessionId}-${uiState.value.lines.size + 1}-${UUID.randomUUID()}"
        runCatching {
            api.lockNextLine(session.sessionId, activeToken, key, energy, mode)
        }.onSuccess { locked ->
            _uiState.update {
                it.copy(
                    pendingLine = locked.line,
                    flow = CastFlowState.ResultLocked,
                    busy = false,
                    animationToken = System.nanoTime(),
                )
            }
            _uiState.update { it.copy(flow = CastFlowState.Animating) }
            playLockedFeedback(locked.line)
        }.onFailure {
            _uiState.update { state ->
                state.copy(error = it.message ?: "起爻失败，请重试。", flow = CastFlowState.Ready, busy = false)
            }
        }
    }

    private fun playLockedFeedback(line: CastLine) {
        viewModelScope.launch {
            val state = uiState.value
            delay(560)
            feedback.coinImpact(0, state.hapticsEnabled, state.soundEnabled)
            delay(200)
            feedback.coinImpact(1, state.hapticsEnabled, state.soundEnabled)
            delay(200)
            feedback.coinImpact(2, state.hapticsEnabled, state.soundEnabled)
            delay(220)
            feedback.lineLocked(line.moving, state.hapticsEnabled, state.soundEnabled)
        }
    }

    private suspend fun completeCast() {
        val session = uiState.value.session ?: return
        val activeToken = token ?: return
        motion.stop()
        _uiState.update { it.copy(flow = CastFlowState.Completing, busy = true) }
        runCatching { api.complete(session.sessionId, activeToken) }
            .onSuccess { completed ->
                _uiState.update {
                    it.copy(
                        completion = completed,
                        lines = completed.lines,
                        flow = CastFlowState.CastComplete,
                        busy = false,
                    )
                }
                val state = uiState.value
                feedback.castComplete(state.hapticsEnabled, state.soundEnabled)
                if (completed.status in pendingStatuses) pollResult() else store.clear()
            }
            .onFailure(::showError)
    }

    private suspend fun fetchOrComplete(status: String) {
        val session = uiState.value.session ?: return
        val activeToken = token ?: return
        runCatching {
            if (status == "ready" || status == "ready_to_complete") {
                api.complete(session.sessionId, activeToken)
            } else {
                api.result(session.sessionId, activeToken)
            }
        }.onSuccess { completed ->
            _uiState.update {
                it.copy(
                    completion = completed,
                    lines = completed.lines,
                    flow = CastFlowState.CastComplete,
                    busy = false,
                )
            }
            if (completed.status in pendingStatuses) pollResult() else store.clear()
        }.onFailure(::showError)
    }

    private fun pollResult() {
        val session = uiState.value.session ?: return
        val activeToken = token ?: return
        viewModelScope.launch {
            repeat(24) {
                delay(2_000)
                val completed = runCatching { api.result(session.sessionId, activeToken) }
                    .getOrElse {
                        _uiState.update { state ->
                            state.copy(error = "解读仍在后台生成，稍后可重新进入查看。")
                        }
                        return@launch
                    }
                _uiState.update { it.copy(completion = completed, lines = completed.lines) }
                if (completed.status !in pendingStatuses) {
                    store.clear()
                    return@launch
                }
            }
        }
    }

    private fun showError(error: Throwable) {
        _uiState.update {
            it.copy(
                busy = false,
                error = error.message ?: "服务暂时不可用，请稍后重试。",
            )
        }
    }

    override fun onCleared() {
        motion.stop()
        feedback.release()
        super.onCleared()
    }

    private companion object {
        val pendingStatuses = setOf("interpretation_pending", "interpreting")
    }
}
