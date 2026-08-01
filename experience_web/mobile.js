const state = {
  config: { motion: { shake_threshold: 11.5, impulses_required: 3, window_ms: 900, cooldown_ms: 1400 } },
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

const $ = selector => document.querySelector(selector);
const setupPanel = $("#setupPanel");
const castPanel = $("#castPanel");
const resultPanel = $("#resultPanel");
const stage = $("#coinStage");
const coins = [...document.querySelectorAll("#coinStage .coin")];

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
  $("#lineProgress").textContent = String(state.lines.length);
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
  $("#lineProgress").textContent = String(state.lines.length);
  $("#completeButton").disabled = state.lines.length !== 6;
}

function hapticFor(line) {
  if (!$("#hapticToggle").checked || typeof navigator.vibrate !== "function") return;
  const pattern = line.moving ? [30, 55, 75] : [24, 45, 24];
  navigator.vibrate(pattern);
}

function animateLine(line) {
  coins.forEach((coin, index) => coin.classList.toggle("reverse", index >= line.fronts));
  if ($("#motionToggle").checked && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    stage.classList.remove("resolving");
    void stage.offsetWidth;
    stage.classList.add("resolving");
  }
  $("#stageHint").textContent = `${line.position_name}：${line.fronts}正${line.reverses}反 · ${line.line_type}`;
  hapticFor(line);
  renderLine(line);
  setTimeout(() => {
    stage.classList.remove("resolving");
    state.busy = false;
  }, 1150);
}

function showError(error) {
  state.busy = false;
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
    if (message.type === "line_locked") animateLine(message.line);
    if (message.type === "cast_completed") showResult(message);
    if (message.type === "error") showError(new Error(message.message));
    if (message.type === "peer_status" && message.role === "desktop" && message.status === "connected") {
      setStatus("已连接电脑", "connected");
    }
  });
}

async function joinPairingCode() {
  const code = $("#pairingCodeInput").value.trim();
  if (!/^\d{6}$/.test(code)) return showError(new Error("请输入六位配对码。"));
  try {
    const pairing = await requestJson("/v1/pairing-sessions/join", {
      method: "POST",
      body: JSON.stringify({ pairing_code: code })
    });
    history.replaceState(null, "", `/mobile?pairing=${encodeURIComponent(pairing.pairing_id)}&token=${encodeURIComponent(pairing.pairing_token)}`);
    connectPairing(pairing.pairing_id, pairing.pairing_token);
  } catch (error) {
    showError(error);
  }
}

async function triggerLine(triggerMode, energy = null) {
  if (state.busy || state.lines.length >= 6) return;
  if (!state.sessionId && !state.pairingId) return showError(new Error("请先创建或加入起卦会话。"));
  state.busy = true;
  $("#stageHint").textContent = "铜钱正在落定…";
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
  $("#energyFill").style.opacity = String(.15 + ratio * .85);
  $("#energyFill").style.transform = `rotate(${Math.round(ratio * 300)}deg)`;
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
    showResult({ ...completed, type: "cast_completed" });
  } catch (error) {
    showError(error);
    $("#completeButton").disabled = false;
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
  $("#resultMeta").textContent = `Run ID · ${(payload.run_id || "").slice(0, 8)} · ${summary.interpretation_status === "completed" ? "解读完成" : "确定性盘面已保留"}`;
  renderInterpretation(
    $("#resultInterpretation"),
    summary.interpretation || "完整盘面已经生成，可回到电脑查看详细证据。"
  );
  setStatus("六爻完成", "connected");
  if ($("#hapticToggle").checked && navigator.vibrate) navigator.vibrate([35, 45, 35, 45, 90]);
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
  const params = new URLSearchParams(location.search);
  const pairingId = params.get("pairing");
  const token = params.get("token");
  if (pairingId && token) connectPairing(pairingId, token);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
}

$("#createSessionButton").addEventListener("click", createDirectSession);
$("#joinCodeButton").addEventListener("click", joinPairingCode);
$("#tapCastButton").addEventListener("click", () => triggerLine("tap"));
$("#motionButton").addEventListener("click", enableMotion);
$("#completeButton").addEventListener("click", completeCast);
$("#settingsButton").addEventListener("click", () => {
  const panel = $("#settingsPanel");
  panel.hidden = !panel.hidden;
  $("#settingsButton").setAttribute("aria-expanded", String(!panel.hidden));
});

boot();
