const state = {
  config: {
    motion: { shake_threshold: 11.5, impulses_required: 3, window_ms: 900, cooldown_ms: 1400 },
    llm: { provider: "deepseek", configured: false, model: "deepseek-v4-flash" }
  },
  sessionId: null,
  sessionToken: null,
  pairingId: null,
  pairingToken: null,
  socket: null,
  lines: [],
  busy: false,
  motionEnabled: false,
  motionListener: null,
  impulses: [],
  lastImpulseAt: 0,
  lastTriggerAt: 0,
  lastMotionVector: null,
  lastImpulseVector: null,
  directionChanges: 0
};

const DIRECT_SESSION_KEY = "shuzhi.direct-session.v1";

const $ = selector => document.querySelector(selector);
const setupPanel = $("#setupPanel");
const castPanel = $("#castPanel");
const resultPanel = $("#resultPanel");
const stage = $("#coinStage");
const coins = [...document.querySelectorAll("#coinStage .single-coin")];
const instrumentArt = stage.querySelector(".instrument-art");
const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const coinRestX = [-78, 0, 78];
const coinRestY = [10, -3, 12];
const coinRestRotation = [-10, 5, 13];
const tossPatterns = [
  { loft: 98, drift: 18, spinX: 720, spinY: 190 },
  { loft: 116, drift: -14, spinX: 1080, spinY: -145 },
  { loft: 92, drift: 11, spinX: 720, spinY: 230 },
  { loft: 108, drift: -19, spinX: 1080, spinY: 170 },
  { loft: 104, drift: 15, spinX: 720, spinY: -210 },
  { loft: 118, drift: -10, spinX: 1080, spinY: 120 }
];

function setStatus(message, kind = "") {
  const badge = $("#connectionBadge");
  badge.textContent = message;
  badge.className = `status-badge ${kind}`.trim();
  $("#liveStatus").textContent = message;
}

async function requestJson(path, options = {}, attempt = 0) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) }
    });
  } catch (error) {
    if (attempt < 5) {
      await new Promise(resolve => setTimeout(resolve, 400 * (attempt + 1)));
      return requestJson(path, options, attempt + 1);
    }
    throw error;
  }
  if (response.headers.get("x-render-routing") === "no-server" && attempt < 5) {
    await new Promise(resolve => setTimeout(resolve, 400 * (attempt + 1)));
    return requestJson(path, options, attempt + 1);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "请求失败，请稍后重试。");
  return payload;
}

function newIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function showCastPanel() {
  setupPanel.hidden = true;
  resultPanel.hidden = true;
  castPanel.hidden = false;
  syncCastProgress();
  const lastLine = state.lines.at(-1);
  $("#stageHint").textContent = lastLine
    ? `${lastLine.position_name}：${lastLine.fronts}正${lastLine.reverses}反 · ${lastLine.line_type}`
    : "轻触铜仪，摇出第一爻";
}

function saveDirectSession() {
  if (!state.sessionId || !state.sessionToken || state.pairingId) return;
  sessionStorage.setItem(DIRECT_SESSION_KEY, JSON.stringify({
    sessionId: state.sessionId,
    sessionToken: state.sessionToken
  }));
}

function clearDirectSession() {
  sessionStorage.removeItem(DIRECT_SESSION_KEY);
}

function lineGlyph(line) {
  return line.value % 2 === 0 ? "⚋" : "⚊";
}

function renderLine(line) {
  if (state.lines.some(item => item.line_index === line.line_index)) return;
  state.lines.push(line);
  state.lines.sort((a, b) => a.line_index - b.line_index);
  const item = document.createElement("li");
  item.className = "line-item";
  const glyph = document.createElement("span");
  glyph.className = "line-glyph";
  glyph.textContent = lineGlyph(line);
  const detail = document.createElement("span");
  detail.className = "line-detail";
  const title = document.createElement("strong");
  title.textContent = `${line.fronts}正${line.reverses}反 · ${line.line_type}${line.moving ? "（动）" : ""}`;
  const source = document.createElement("small");
  source.textContent = line.trigger_mode === "motion" ? "体感触发" : line.trigger_mode === "paired" ? "手机协同" : "点按触发";
  detail.append(title, source);
  const position = document.createElement("span");
  position.className = "line-position";
  position.textContent = line.position_name;
  item.append(glyph, detail, position);
  $("#lineList").append(item);
  syncCastProgress();
}

function syncCastProgress() {
  const count = state.lines.length;
  const next = Math.min(count + 1, 6);
  $("#lineProgress").textContent = String(count);
  $("#nextLineNumber").textContent = String(next);
  $("#lineDots").setAttribute("aria-label", `已完成 ${count} 爻`);
  document.querySelectorAll("[data-line-slot]").forEach((slot, index) => {
    slot.classList.toggle("is-complete", index < count);
  });
  $("#tapCastButton").textContent = count < 6 ? `摇第 ${next} 爻` : "六爻已成";
  $("#tapCastButton").disabled = state.busy || count >= 6;
  $("#motionButton").disabled = state.busy || count >= 6;
  $("#completeButton").disabled = state.busy || count !== 6;
  $("#guidanceTitle").textContent = count === 6 ? "六爻已成，天机可读" : "握稳手机，专注所问";
  $("#guidanceCopy").textContent = count === 6
    ? "系统已完成本卦、变卦与时空信息校验。"
    : "可直接点按，也可启用体感后轻轻摇动手机。";
}

function setCastBusy(busy) {
  state.busy = busy;
  syncCastProgress();
  if (busy) $("#tapCastButton").textContent = "正在听钱落定…";
}

function hapticFor(line) {
  if (!$("#hapticToggle").checked || typeof navigator.vibrate !== "function") return;
  const pattern = line.moving ? [30, 55, 75] : [24, 45, 24];
  navigator.vibrate(pattern);
}

function interpretationLabel(summary) {
  if (summary.interpretation_status === "failed") return "DeepSeek 调用失败 · 确定性盘面已保留";
  if (summary.ai_generated && summary.interpretation_mode === "api") return "DeepSeek 解读完成";
  return "离线规则解读 · 未调用 DeepSeek";
}

function vibrateResult() {
  if (!$("#hapticToggle").checked || typeof navigator.vibrate !== "function") return false;
  return navigator.vibrate([35, 45, 35, 45, 100]);
}

function coinTransform(x, y, rotateX, rotateY, rotateZ, scale) {
  return `translate3d(${x}px, ${y}px, 0) rotateX(${rotateX}deg) rotateY(${rotateY}deg) rotateZ(${rotateZ}deg) scale(${scale})`;
}

function animateLine(line) {
  const simplify = reducedMotion() || !$("#motionToggle").checked;
  const settleAfter = simplify ? 180 : 1420;
  const tossIndex = Math.max(0, Number(line.line_index || state.lines.length + 1) - 1);
  $("#stageHint").textContent = "铜钱翻转中…";

  coins.forEach((coin, index) => {
    const pattern = tossPatterns[(tossIndex + index * 2) % tossPatterns.length];
    const restX = coinRestX[index];
    const restY = coinRestY[index];
    const restRotation = coinRestRotation[index];
    const side = index === 0 ? 1 : -1;
    coin.classList.remove("reverse");
    coin.getAnimations().forEach(animation => animation.cancel());
    const settled = coinTransform(restX, restY, 0, 0, restRotation, 1);
    const keyframes = simplify ? [
      { transform: settled, opacity: .7 },
      { transform: coinTransform(restX, restY - 8, 0, 0, restRotation, 1.03), opacity: 1 },
      { transform: settled, opacity: 1 }
    ] : [
      { transform: settled },
      { transform: coinTransform(restX + pattern.drift * side, restY - pattern.loft * .72, pattern.spinX * .28, pattern.spinY * .35, restRotation + 12 * side, 1.05) },
      { transform: coinTransform(restX + pattern.drift, restY - pattern.loft, pattern.spinX * .68, pattern.spinY, restRotation - 8 * side, 1.09) },
      { transform: coinTransform(restX - pattern.drift * .25, restY + 15, pattern.spinX - 28, pattern.spinY * .4, restRotation + 5, .94) },
      { transform: coinTransform(restX, restY - 7, pattern.spinX + 18, 8 * side, restRotation - 2, 1.025) },
      { transform: coinTransform(restX, restY, pattern.spinX, 0, restRotation, 1) }
    ];
    coin.animate(keyframes, {
      duration: simplify ? 160 : 1280 + index * 55,
      delay: simplify ? 0 : index * 45,
      easing: "cubic-bezier(.2,.76,.25,1)",
      fill: "none"
    });
  });

  if (!simplify) {
    instrumentArt.getAnimations().forEach(animation => animation.cancel());
    instrumentArt.animate([
      { transform: "scale(1)", opacity: .66 },
      { transform: "scale(1.018)", opacity: .76 },
      { transform: "scale(1.006)", opacity: .7 },
      { transform: "scale(1)", opacity: .66 }
    ], { duration: 1380, easing: "cubic-bezier(.22,.72,.24,1)" });
  }

  setTimeout(() => {
    coins.forEach((coin, index) => coin.classList.toggle("reverse", index >= line.fronts));
    $("#stageHint").textContent = `${line.position_name}：${line.fronts}正${line.reverses}反 · ${line.line_type}`;
    hapticFor(line);
    renderLine(line);
    setCastBusy(false);
  }, settleAfter);
}

function showError(error) {
  setCastBusy(false);
  setStatus(error.message || String(error), "error");
  $("#stageHint").textContent = error.message || String(error);
}

async function createDirectSession() {
  const question = $("#questionInput").value.trim();
  if (!question) return showError(new Error("请先写下本次占问事项。"));
  try {
    const session = await requestJson("/v1/cast-sessions", {
      method: "POST",
      body: JSON.stringify({ question })
    });
    state.sessionId = session.session_id;
    state.sessionToken = session.session_token;
    saveDirectSession();
    showCastPanel();
    setStatus("手机独立起卦", "connected");
  } catch (error) {
    showError(error);
  }
}

function websocketUrl(pairingId, token) {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/v1/pairing-sessions/${pairingId}/ws?token=${encodeURIComponent(token)}&role=mobile`;
}

function connectPairing(pairingId, token, attempt = 0) {
  state.pairingId = pairingId;
  state.pairingToken = token;
  showCastPanel();
  setStatus("正在连接电脑…");
  const socket = new WebSocket(websocketUrl(pairingId, token));
  state.socket = socket;
  socket.addEventListener("open", () => setStatus("已连接电脑", "connected"));
  socket.addEventListener("close", () => {
    if (state.socket !== socket) return;
    if (state.lines.length < 6 && attempt < 6) {
      setStatus("连接波动，正在自动重连…");
      setTimeout(() => connectPairing(pairingId, token, attempt + 1), 500 * (attempt + 1));
      return;
    }
    setStatus("电脑连接已断开", "error");
    if (state.lines.length < 6) $("#stageHint").textContent = "连接中断，请回到电脑重新扫码。";
  });
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.type === "session_snapshot") {
      state.lines = [];
      $("#lineList").replaceChildren();
      (message.lines || []).forEach(renderLine);
      const completion = message.completion;
      if (completion) {
        if (["interpretation_pending", "interpreting"].includes(completion.status)) {
          showPendingResult(completion);
        } else {
          showResult(completion);
        }
      } else {
        showCastPanel();
        setStatus(`协同进度已恢复 · ${state.lines.length} / 6 爻`, "connected");
      }
    }
    if (message.type === "line_locked") animateLine(message.line);
    if (message.type === "cast_prepared") showPendingResult(message);
    if (message.type === "cast_completed") showResult(message);
    if (message.type === "error") showError(new Error(message.message));
    if (message.type === "peer_status" && message.role === "desktop" && message.status === "connected") {
      setStatus("已连接电脑", "connected");
    }
  });
}

async function triggerLine(triggerMode, energy = null) {
  if (state.busy || state.lines.length >= 6) return;
  if (!state.sessionId && !state.pairingId) return showError(new Error("请先创建或加入起卦会话。"));
  setCastBusy(true);
  $("#stageHint").textContent = "正在感应铜钱…";
  if ($("#hapticToggle").checked && typeof navigator.vibrate === "function") navigator.vibrate(18);
  const idempotencyKey = newIdempotencyKey();
  try {
    if (state.pairingId) {
      if (!state.socket || state.socket.readyState !== WebSocket.OPEN) throw new Error("电脑连接尚未就绪。请稍后再试。");
      state.socket.send(JSON.stringify({
        type: "lock_line",
        idempotency_key: idempotencyKey,
        trigger_mode: triggerMode,
        motion_energy: energy
      }));
      return;
    }
    const payload = await requestJson(`/v1/cast-sessions/${state.sessionId}/lines`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${state.sessionToken}`,
        "Idempotency-Key": idempotencyKey
      },
      body: JSON.stringify({ trigger_mode: triggerMode, motion_energy: energy })
    });
    animateLine(payload.line);
  } catch (error) {
    showError(error);
  }
}

function motionSample(event) {
  const source = event.acceleration;
  if (source && [source.x, source.y, source.z].every(Number.isFinite)) {
    const vector = [source.x, source.y, source.z];
    return { energy: Math.hypot(...vector), vector };
  }
  const gravity = event.accelerationIncludingGravity;
  if (gravity && [gravity.x, gravity.y, gravity.z].every(Number.isFinite)) {
    const current = [gravity.x, gravity.y, gravity.z];
    const previous = state.lastMotionVector;
    state.lastMotionVector = current;
    if (!previous) return { energy: 0, vector: current };
    const vector = current.map((value, index) => value - previous[index]);
    return { energy: Math.hypot(...vector), vector };
  }
  return { energy: 0, vector: null };
}

function changedDirection(previous, current) {
  if (!previous || !current) return false;
  const denominator = Math.hypot(...previous) * Math.hypot(...current);
  if (!denominator) return false;
  const cosine = previous.reduce((sum, value, index) => sum + value * current[index], 0) / denominator;
  return cosine < .55;
}

function handleMotion(event) {
  if (!state.motionEnabled || state.busy || state.lines.length >= 6) return;
  const now = performance.now();
  const sample = motionSample(event);
  const energy = sample.energy;
  const cfg = state.config.motion;
  const ratio = Math.min(1, energy / cfg.shake_threshold);
  stage.style.setProperty("--motion-energy", String(ratio));
  if (energy < cfg.shake_threshold || now - state.lastImpulseAt < 120) return;
  state.lastImpulseAt = now;
  if (changedDirection(state.lastImpulseVector, sample.vector)) state.directionChanges += 1;
  state.lastImpulseVector = sample.vector;
  state.impulses.push(now);
  state.impulses = state.impulses.filter(time => now - time <= cfg.window_ms);
  if (
    state.impulses.length >= cfg.impulses_required &&
    state.directionChanges >= 1 &&
    state.impulses.at(-1) - state.impulses[0] >= 240 &&
    now - state.lastTriggerAt >= cfg.cooldown_ms
  ) {
    state.lastTriggerAt = now;
    state.impulses = [];
    state.directionChanges = 0;
    state.lastImpulseVector = null;
    triggerLine("motion", Math.min(100, Math.round(energy / cfg.shake_threshold * 55)));
  }
}

async function enableMotion() {
  try {
    if (typeof DeviceMotionEvent === "undefined") throw new Error("当前设备没有开放运动传感器，请使用点按摇卦。 ");
    if (typeof DeviceMotionEvent.requestPermission === "function") {
      const permission = await DeviceMotionEvent.requestPermission();
      if (permission !== "granted") throw new Error("运动权限未开启，已经为你保留点按摇卦。 ");
    }
    if (!state.motionListener) {
      state.motionListener = handleMotion;
      window.addEventListener("devicemotion", state.motionListener, { passive: true });
    }
    state.motionEnabled = true;
    $("#motionButton").textContent = "体感已启用 · 轻轻摇动手机";
    $("#stageHint").textContent = "连续轻摇，达到识别阈值后自动生成一爻";
    setStatus(state.pairingId ? "体感已启用 · 已连接电脑" : "体感已启用", "connected");
  } catch (error) {
    showError(error);
  }
}

async function completeCast() {
  if (state.lines.length !== 6 || state.busy) return;
  state.busy = true;
  $("#completeButton").disabled = true;
  setStatus("正在生成确定性盘面…");
  try {
    if (state.pairingId) {
      state.socket.send(JSON.stringify({ type: "complete" }));
      return;
    }
    const completed = await requestJson(`/v1/cast-sessions/${state.sessionId}/complete`, {
      method: "POST",
      headers: { Authorization: `Bearer ${state.sessionToken}` }
    });
    if (["interpretation_pending", "interpreting"].includes(completed.status)) {
      showPendingResult(completed);
      pollDirectResult();
    } else {
      showResult({ ...completed, type: "cast_completed" });
    }
  } catch (error) {
    showError(error);
    $("#completeButton").disabled = false;
  }
}

function showPendingResult(payload) {
  state.busy = false;
  const summary = payload.result_summary || {};
  castPanel.hidden = true;
  resultPanel.hidden = false;
  $("#resultTitle").textContent = summary.changed_hexagram_name
    ? `${summary.hexagram_name || "本卦"} → ${summary.changed_hexagram_name}`
    : summary.hexagram_name || "盘面已完成";
  $("#resultMeta").textContent = `Run ID · ${(payload.run_id || "").slice(0, 8)} · DeepSeek 解读生成中`;
  renderInterpretation(
    $("#resultInterpretation"),
    summary.interpretation || "确定性盘面已完成，DeepSeek 正在后台生成白话解读。"
  );
  $("#resultHapticButton").hidden = true;
  $("#resultHapticStatus").textContent = "你可以停留在本页，解读完成后会自动更新。";
  setStatus("盘面完成 · 解读生成中", "connected");
}

async function pollDirectResult(attempt = 0) {
  if (!state.sessionId || !state.sessionToken || state.pairingId) return;
  try {
    const result = await requestJson(`/v1/cast-sessions/${state.sessionId}/result`, {
      headers: { Authorization: `Bearer ${state.sessionToken}` }
    });
    if (["interpretation_pending", "interpreting"].includes(result.status)) {
      if (attempt < 90) setTimeout(() => pollDirectResult(attempt + 1), 1200);
      return;
    }
    showResult(result);
  } catch (error) {
    if (attempt < 8) {
      setTimeout(() => pollDirectResult(attempt + 1), 1500);
      return;
    }
    showError(error);
  }
}

async function restoreDirectSession() {
  const stored = sessionStorage.getItem(DIRECT_SESSION_KEY);
  if (!stored) return false;
  try {
    const saved = JSON.parse(stored);
    if (!saved.sessionId || !saved.sessionToken) throw new Error("恢复信息不完整。");
    state.sessionId = saved.sessionId;
    state.sessionToken = saved.sessionToken;
    const session = await requestJson(`/v1/cast-sessions/${state.sessionId}`, {
      headers: { Authorization: `Bearer ${state.sessionToken}` }
    });
    state.lines = [];
    $("#lineList").replaceChildren();
    session.lines.forEach(renderLine);
    if (["interpretation_pending", "interpreting", "completed", "interpretation_failed"].includes(session.status)) {
      const result = await requestJson(`/v1/cast-sessions/${state.sessionId}/result`, {
        headers: { Authorization: `Bearer ${state.sessionToken}` }
      });
      if (["interpretation_pending", "interpreting"].includes(result.status)) {
        showPendingResult(result);
        pollDirectResult();
      } else {
        showResult(result);
      }
    } else {
      showCastPanel();
      setStatus(`已恢复 · ${state.lines.length} / 6 爻`, "connected");
    }
    return true;
  } catch (_) {
    clearDirectSession();
    state.sessionId = null;
    state.sessionToken = null;
    return false;
  }
}

function showResult(payload) {
  state.busy = false;
  if (state.motionListener) window.removeEventListener("devicemotion", state.motionListener);
  const summary = payload.result_summary || {};
  castPanel.hidden = true;
  resultPanel.hidden = false;
  $("#resultTitle").textContent = summary.changed_hexagram_name
    ? `${summary.hexagram_name || "本卦"} → ${summary.changed_hexagram_name}`
    : summary.hexagram_name || "排盘完成";
  $("#resultMeta").textContent = `Run ID · ${(payload.run_id || "").slice(0, 8)} · ${interpretationLabel(summary)}`;
  renderInterpretation(
    $("#resultInterpretation"),
    summary.interpretation || (state.pairingId
      ? "完整盘面已经生成，可回到电脑查看详细证据。"
      : "完整盘面已经生成，可在本页查看解读与六爻结果。")
  );
  setStatus("六爻完成", "connected");
  const hapticButton = $("#resultHapticButton");
  const hapticStatus = $("#resultHapticStatus");
  if (typeof navigator.vibrate === "function" && $("#hapticToggle").checked) {
    hapticButton.hidden = false;
    hapticStatus.textContent = vibrateResult()
      ? "已发送结果触觉；若未感到震动，可点“触觉确认”重试。"
      : "浏览器拦截了自动震动，请点“触觉确认”。";
  } else {
    hapticButton.hidden = true;
    hapticStatus.textContent = "当前浏览器不支持网页震动；iPhone Safari 需使用微信小程序或原生 App 才能提供可靠触觉。";
  }
}

function renderInterpretation(container, text) {
  container.replaceChildren();
  String(text).split(/\n+/).map(line => line.trim()).filter(Boolean).forEach(line => {
    const heading = line.match(/^#{1,6}\s+(.+)$/);
    const element = document.createElement(heading ? "h3" : "p");
    element.textContent = (heading ? heading[1] : line).replace(/^\*\*(.+)\*\*$/, "$1");
    container.append(element);
  });
}

async function boot() {
  try { state.config = await requestJson("/v1/config"); } catch (_) { /* use safe defaults */ }
  if (typeof navigator.vibrate !== "function") {
    $("#hapticToggle").checked = false;
    $("#hapticToggle").disabled = true;
  }
  const params = new URLSearchParams(location.search);
  const pairingId = params.get("pairing");
  const token = params.get("token");
  if (pairingId && token) {
    connectPairing(pairingId, token);
  } else {
    await restoreDirectSession();
  }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
}

$("#createSessionButton").addEventListener("click", createDirectSession);
$("#tapCastButton").addEventListener("click", () => triggerLine("tap"));
$("#motionButton").addEventListener("click", enableMotion);
$("#completeButton").addEventListener("click", completeCast);
$("#resultHapticButton").addEventListener("click", () => {
  $("#resultHapticStatus").textContent = vibrateResult()
    ? "触觉确认已发送。"
    : "当前浏览器或系统未执行震动。";
});
$("#newCastLink").addEventListener("click", clearDirectSession);
$("#settingsButton").addEventListener("click", () => {
  const panel = $("#settingsPanel");
  panel.hidden = !panel.hidden;
  $("#settingsButton").setAttribute("aria-expanded", String(!panel.hidden));
});

$("#questionInput").addEventListener("input", event => {
  $("#questionCount").textContent = String(event.target.value.length);
});

document.querySelectorAll(".intent-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".intent-chip").forEach(item => item.classList.remove("is-active"));
    chip.classList.add("is-active");
  });
});

boot();
