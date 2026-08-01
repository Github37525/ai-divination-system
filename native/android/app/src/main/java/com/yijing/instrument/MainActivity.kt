package com.yijing.instrument

import android.animation.ValueAnimator
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val model: CastViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            InstrumentTheme {
                InstrumentApp(model)
            }
        }
    }
}

private object InstrumentColors {
    val Ink = Color(0xFF071017)
    val Panel = Color(0xFF0E1A20)
    val Bronze = Color(0xFFC39145)
    val PaleBronze = Color(0xFFE5C37A)
    val Jade = Color(0xFF4DB8AA)
    val Paper = Color(0xFFE0DCC5)
}

@Composable
private fun InstrumentTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = MaterialTheme.colorScheme.copy(
            primary = InstrumentColors.PaleBronze,
            secondary = InstrumentColors.Jade,
            background = InstrumentColors.Ink,
            surface = InstrumentColors.Panel,
            onPrimary = InstrumentColors.Ink,
            onBackground = InstrumentColors.Paper,
            onSurface = InstrumentColors.Paper,
        ),
        content = content,
    )
}

@Composable
private fun InstrumentApp(model: CastViewModel) {
    val state by model.uiState.collectAsStateWithLifecycle()
    Box(Modifier.fillMaxSize()) {
        Starfield()
        when {
            state.completion != null -> ResultScreen(model, state, state.completion)
            state.session != null -> CastScreen(model, state)
            else -> QuestionScreen(model, state)
        }
    }
    state.error?.let { message ->
        AlertDialog(
            onDismissRequest = model::clearError,
            confirmButton = { TextButton(onClick = model::clearError) { Text("知道了") } },
            title = { Text("未能完成") },
            text = { Text(message) },
        )
    }
}

@Composable
private fun Starfield() {
    Box(
        Modifier
            .fillMaxSize()
            .background(
                Brush.radialGradient(
                    listOf(InstrumentColors.Jade.copy(alpha = 0.15f), InstrumentColors.Ink),
                    radius = 1_200f,
                ),
            ),
    ) {
        Canvas(Modifier.fillMaxSize()) {
            repeat(42) { index ->
                val x = ((index * 73) % 101) / 101f * size.width
                val y = ((index * 47) % 97) / 97f * size.height
                drawCircle(
                    color = InstrumentColors.PaleBronze.copy(alpha = 0.24f),
                    radius = if (index % 7 == 0) 1.5f else 0.8f,
                    center = androidx.compose.ui.geometry.Offset(x, y),
                )
            }
        }
    }
}

@Composable
private fun QuestionScreen(model: CastViewModel, state: CastUiState) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 34.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        Text("天文铜仪", fontSize = 40.sp, fontWeight = FontWeight.SemiBold, color = InstrumentColors.PaleBronze)
        Text("以手机动作触发 · 以服务端规则锁定", color = InstrumentColors.Paper.copy(alpha = 0.66f))

        InstrumentPanel {
            Text("你此刻想理清什么？", fontWeight = FontWeight.SemiBold)
            OutlinedTextField(
                value = state.question,
                onValueChange = model::updateQuestion,
                modifier = Modifier.fillMaxWidth().height(142.dp),
                placeholder = { Text("请用一句话描述当前问题") },
                shape = RoundedCornerShape(16.dp),
            )
            Button(
                onClick = model::startSession,
                enabled = state.question.isNotBlank() && !state.busy,
                modifier = Modifier.fillMaxWidth().height(54.dp),
                shape = RoundedCornerShape(17.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = InstrumentColors.PaleBronze,
                    contentColor = InstrumentColors.Ink,
                ),
            ) {
                if (state.busy) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(10.dp))
                }
                Text(if (state.busy) "正在建立会话" else "填写完成，开始摇卦", fontWeight = FontWeight.SemiBold)
            }
        }

        Column(
            modifier = Modifier.alpha(0.72f),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("• 京房纳甲六爻")
            Text("• 真太阳时与历法规则由服务端统一计算")
            Text("• AI 不参与排盘，只解释已经锁定的结果")
        }
    }
}

@Composable
private fun CastScreen(model: CastViewModel, state: CastUiState) {
    val energy by model.motion.energy.collectAsStateWithLifecycle()
    val ready by model.motion.ready.collectAsStateWithLifecycle()
    val calibration by model.motion.calibrationProgress.collectAsStateWithLifecycle()

    DisposableEffect(state.session?.sessionId) {
        model.motion.start()
        onDispose { model.motion.stop() }
    }

    val count = state.lines.size + if (state.pendingLine == null) 0 else 1
    val canTrigger = ready && state.pendingLine == null && state.lines.size < 6 && !state.busy &&
        (state.flow == CastFlowState.Ready || state.flow == CastFlowState.LineComplete)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(state.flow.label, fontSize = 22.sp, fontWeight = FontWeight.SemiBold, color = InstrumentColors.PaleBronze)
                Text(
                    statusDetail(state, model.motion.isAvailable, ready, calibration),
                    fontSize = 12.sp,
                    color = InstrumentColors.Paper.copy(alpha = 0.62f),
                )
            }
            Text(
                "$count/6",
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.SemiBold,
                color = InstrumentColors.Jade,
                modifier = Modifier
                    .clip(CircleShape)
                    .background(InstrumentColors.Jade.copy(alpha = 0.10f))
                    .padding(horizontal = 12.dp, vertical = 7.dp),
            )
        }

        InstrumentPanel { CoinStage(model, state, energy) }
        InstrumentPanel { LineProgress(state.lines, state.pendingLine) }

        Button(
            onClick = model::tapFallback,
            enabled = canTrigger,
            modifier = Modifier.fillMaxWidth().height(50.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = InstrumentColors.PaleBronze,
                contentColor = InstrumentColors.Ink,
            ),
        ) {
            Text("点按起第 ${minOf(state.lines.size + 1, 6)} 爻", fontWeight = FontWeight.SemiBold)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
            LabeledSwitch("音效", state.soundEnabled, model::setSoundEnabled)
            LabeledSwitch("触觉", state.hapticsEnabled, model::setHapticsEnabled)
        }
    }
}

private fun statusDetail(
    state: CastUiState,
    sensorsAvailable: Boolean,
    ready: Boolean,
    calibration: Double,
): String = when {
    !sensorsAvailable -> "本机无可用动作传感器，请使用点按起爻。"
    !ready -> "请平稳握持片刻 · ${(calibration * 100).toInt()}%"
    state.pendingLine != null -> "结果已先锁定，正在呈现三枚铜钱。"
    else -> "自然摇动手机三次，或使用点按起爻。"
}

@Composable
private fun CoinStage(model: CastViewModel, state: CastUiState, energy: Double) {
    val animationsEnabled = remember { ValueAnimator.areAnimatorsEnabled() }
    val pending = state.pendingLine

    LaunchedEffect(state.animationToken) {
        if (pending != null && state.animationToken != 0L) {
            delay(if (animationsEnabled) 1_480 else 360)
            model.animationCompleted()
        }
    }

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.fillMaxWidth().height(274.dp), contentAlignment = Alignment.Center) {
            Canvas(Modifier.size(258.dp)) {
                drawCircle(InstrumentColors.Bronze.copy(alpha = 0.18f), style = androidx.compose.ui.graphics.drawscope.Stroke(1.dp.toPx()))
                drawArc(
                    color = InstrumentColors.Jade,
                    startAngle = -90f,
                    sweepAngle = (energy.coerceAtLeast(5.0) / 100 * 360).toFloat(),
                    useCenter = false,
                    style = androidx.compose.ui.graphics.drawscope.Stroke(2.dp.toPx()),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy((-6).dp)) {
                repeat(3) { index ->
                    CoinVisual(
                        index = index,
                        animationToken = state.animationToken,
                        isFront = pending == null || index < pending.fronts,
                        showFace = pending != null,
                        animationsEnabled = animationsEnabled,
                    )
                }
            }
        }
        val label = pending?.let { "${it.fronts} 正 · ${it.reverses} 反 · ${it.lineType}" }
            ?: "动作能量 ${energy.toInt()}"
        Text(
            label,
            fontFamily = FontFamily.Monospace,
            fontWeight = FontWeight.Medium,
            color = if (pending == null) InstrumentColors.Paper.copy(alpha = 0.55f) else InstrumentColors.PaleBronze,
            modifier = Modifier.semantics { contentDescription = label },
        )
    }
}

@Composable
private fun CoinVisual(
    index: Int,
    animationToken: Long,
    isFront: Boolean,
    showFace: Boolean,
    animationsEnabled: Boolean,
) {
    val y = remember { Animatable(46f) }
    val x = remember { Animatable(0f) }
    val rotationX = remember { Animatable(0f) }
    val rotationZ = remember { Animatable((index - 1) * 7f) }

    LaunchedEffect(animationToken) {
        if (animationToken == 0L) return@LaunchedEffect
        if (!animationsEnabled) {
            y.snapTo(18f + index * 3f)
            x.snapTo((index - 1) * 8f)
            rotationX.snapTo(if (isFront) 720f else 900f)
            return@LaunchedEffect
        }
        y.snapTo(46f)
        x.snapTo(0f)
        rotationX.snapTo(0f)
        coroutineScope {
            launch {
                y.animateTo(-54f - index * 7f, spring(dampingRatio = 0.70f, stiffness = 460f))
                y.animateTo(-76f - (2 - index) * 8f, tween(220))
                y.animateTo(30f + index * 4f, tween(360))
                y.animateTo(18f + index * 3f, spring(dampingRatio = 0.62f, stiffness = 380f))
            }
            launch {
                x.animateTo((index - 1) * 18f, tween(260))
                x.animateTo((index - 1) * 8f, spring(dampingRatio = 0.72f, stiffness = 360f))
            }
            launch {
                rotationX.animateTo(510f + index * 72f, tween(510))
                rotationX.animateTo(if (isFront) 720f else 900f, tween(530))
            }
            launch {
                rotationZ.animateTo((index - 1) * 34f, tween(500))
                rotationZ.animateTo((index - 1) * 9f, spring(dampingRatio = 0.70f, stiffness = 340f))
            }
        }
    }

    Box(
        modifier = Modifier
            .size(96.dp)
            .graphicsLayer {
                translationX = x.value.dp.toPx()
                translationY = y.value.dp.toPx()
                this.rotationX = rotationX.value
                this.rotationZ = rotationZ.value
                cameraDistance = 14f * density
                shadowElevation = if (showFace) 8.dp.toPx() else 18.dp.toPx()
            },
        contentAlignment = Alignment.Center,
    ) {
        Image(
            painter = painterResource(R.drawable.bronze_coin),
            contentDescription = null,
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Fit,
        )
        if (showFace) {
            Text(
                if (isFront) "正" else "反",
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold,
                color = Color.Black.copy(alpha = 0.68f),
                modifier = Modifier
                    .background(InstrumentColors.PaleBronze.copy(alpha = 0.76f), CircleShape)
                    .padding(6.dp),
            )
        }
    }
}

@Composable
private fun LineProgress(lines: List<CastLine>, pending: CastLine?) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        for (index in 6 downTo 1) {
            val line = if (pending?.lineIndex == index) pending else lines.firstOrNull { it.lineIndex == index }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(positionName(index), fontSize = 12.sp, color = InstrumentColors.Paper.copy(alpha = 0.48f), modifier = Modifier.width(42.dp))
                LineGlyph(line, Modifier.weight(1f))
                Text(
                    line?.lineType ?: "待开始",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = when {
                        line == null -> InstrumentColors.Paper.copy(alpha = 0.28f)
                        line.moving -> InstrumentColors.Jade
                        else -> InstrumentColors.Paper
                    },
                    modifier = Modifier.width(56.dp),
                )
            }
        }
    }
}

@Composable
private fun LineGlyph(line: CastLine?, modifier: Modifier = Modifier) {
    val color = when {
        line == null -> InstrumentColors.Paper.copy(alpha = 0.12f)
        line.moving -> InstrumentColors.Jade
        else -> InstrumentColors.PaleBronze
    }
    Row(modifier.height(7.dp), horizontalArrangement = Arrangement.spacedBy(if (line?.isYang == true) 0.dp else 13.dp)) {
        Box(Modifier.weight(1f).fillMaxSize().background(color, CircleShape))
        if (line?.isYang != true) Box(Modifier.weight(1f).fillMaxSize().background(color, CircleShape))
    }
}

@Composable
private fun ResultScreen(model: CastViewModel, state: CastUiState, completion: CompletionResponse?) {
    if (completion == null) return
    val summary = completion.summary
    val title = if (!summary.changedHexagramName.isNullOrBlank()) {
        "${summary.hexagramName ?: "本卦"} → ${summary.changedHexagramName}"
    } else summary.hexagramName ?: "六爻完成"
    val interpretationStage = when (completion.status) {
        "interpretation_pending", "interpreting" -> "生成白话解读 · 可稍后回来"
        "interpretation_failed" -> "解读暂未完成 · 盘面已保留"
        else -> if (summary.aiGenerated) "DeepSeek 解读完成" else "规则解读完成"
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Text("盘面已锁定", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = InstrumentColors.Jade)
        Text(title, fontSize = 34.sp, fontWeight = FontWeight.SemiBold, color = InstrumentColors.PaleBronze)
        InstrumentPanel { LineProgress(completion.lines, null) }
        InstrumentPanel {
            Text(interpretationStage, fontWeight = FontWeight.SemiBold, color = InstrumentColors.Jade)
            Text(summary.interpretation ?: "确定性盘面已可查看，DeepSeek 正在后台生成白话解读。")
        }
        InstrumentPanel {
            Text("可核验信息", fontWeight = FontWeight.SemiBold)
            Text("算法 ${completion.algorithmVersion} · Run ID ${completion.runId.take(8)}", fontSize = 12.sp, color = InstrumentColors.Paper.copy(alpha = 0.62f))
            val moving = completion.lines.filter { it.moving }.joinToString("、") { it.positionName }.ifEmpty { "无" }
            Text("动爻：$moving", fontSize = 12.sp, color = InstrumentColors.Paper.copy(alpha = 0.62f))
            Text("AI 只解释已锁定盘面，不改变卦象。", fontSize = 12.sp, color = InstrumentColors.Paper.copy(alpha = 0.62f))
        }
        Button(onClick = model::reset, modifier = Modifier.fillMaxWidth().height(50.dp)) {
            Text("完成并开始新的问题")
        }
    }
}

@Composable
private fun InstrumentPanel(content: @Composable ColumnScope.() -> Unit) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, InstrumentColors.Bronze.copy(alpha = 0.28f), RoundedCornerShape(24.dp)),
        shape = RoundedCornerShape(24.dp),
        color = InstrumentColors.Panel.copy(alpha = 0.94f),
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            content()
        }
    }
}

@Composable
private fun LabeledSwitch(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(label, fontSize = 12.sp, color = InstrumentColors.Paper.copy(alpha = 0.75f))
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

private fun positionName(index: Int) = listOf("初爻", "二爻", "三爻", "四爻", "五爻", "上爻")[index - 1]
