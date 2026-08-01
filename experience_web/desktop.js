const desktopState = {
  pairingId: null,
  pairingToken: null,
  mobileUrl: null,
  socket: null,
  lines: [],
  busy: false
};

const $d = selector => document.querySelector(selector);
const desktopStage = $d("#desktopCoinStage");
const desktopCoins = [...document.querySelectorAll("#desktopCoinStage .coin")];

function desktopStatus(message, kind = "") {
  const badge = $d("#desktopConnectionBadge");
  badge.textContent = message;
  badge.className = `status-badge ${kind}`.trim();
  $d("#desktopLiveStatus").textContent = message;
}

async function desktopRequest(path, options = {}, attempt = 0) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) }
    });
  } catch (error) {
    if (attempt < 5) {
      await new Promise(resolve => setTimeout(resolve, 400 * (attempt + 1)));
      return desktopRequest(path, options, attempt + 1);
    }
    throw error;
  }
  if (response.headers.get("x-render-routing") === "no-server" && attempt < 5) {
    await new Promise(resolve => setTimeout(resolve, 400 * (attempt + 1)));
    return desktopRequest(path, options, attempt + 1);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "请求失败，请稍后重试。");
  return payload;
}

function desktopWebsocketUrl(pairing) {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/v1/pairing-sessions/${pairing.pairing_id}/ws?token=${encodeURIComponent(pairing.pairing_token)}&role=desktop`;
}

function renderQr(qrUrl) {
  const target = $d("#qrCode");
  target.replaceChildren();
  const image = document.createElement("img");
  image.src = qrUrl;
  image.alt = "手机配对二维码";
  image.width = 194;
  image.height = 194;
  image.addEventListener("error", () => {
    image.remove();
    const fallback = document.createElement("p");
    fallback.style.color = "#07101f";
    fallback.textContent = "二维码暂时不可用，请复制下方手机链接或输入配对码。";
    target.append(fallback);
  }, { once: true });
  target.append(image);
}

async function createPairing() {
  const question = $d("#desktopQuestion").value.trim();
  if (!question) return desktopStatus("请先写下本次占问事项。", "error");
  try {
    desktopStatus("正在创建安全配对…");
    const pairing = await desktopRequest("/v1/pairing-sessions", {
      method: "POST",
      body: JSON.stringify({ question })
    });
    desktopState.pairingId = pairing.pairing_id;
    desktopState.pairingToken = pairing.pairing_token;
    desktopState.mobileUrl = pairing.mobile_url;
    $d("#pairingDetails").hidden = false;
    $d("#pairingCode").textContent = pairing.pairing_code;
    $d("#pairingExpiry").textContent = `配对入口将在 ${new Date(pairing.expires_at).toLocaleTimeString()} 前有效`;
    $d("#desktopRunId").textContent = `RUN · ${pairing.run_id.slice(0, 8)}`;
    renderQr(pairing.qr_url);
    connectDesktopSocket(pairing);
  } catch (error) {
    desktopStatus(error.message, "error");
  }
}

function connectDesktopSocket(pairing, attempt = 0) {
  if (desktopState.socket) desktopState.socket.close();
  const socket = new WebSocket(desktopWebsocketUrl(pairing));
  desktopState.socket = socket;
  socket.addEventListener("open", () => {
    desktopStatus("配对已创建 · 等待手机", "connected");
    $d("#desktopHint").textContent = "用手机扫描左侧二维码，或输入六位配对码";
  });
  socket.addEventListener("close", () => {
    if (desktopState.socket !== socket) return;
    if (desktopState.lines.length < 6 && attempt < 6) {
      desktopStatus("连接波动，正在自动重连…");
      setTimeout(() => connectDesktopSocket(pairing, attempt + 1), 500 * (attempt + 1));
      return;
    }
    desktopStatus("协同连接已断开", "error");
  });
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.type === "peer_status" && message.role === "mobile") {
      if (message.status === "connected") {
        desktopStatus("手机已连接", "connected");
        $d("#desktopHint").textContent = "手机已就绪，轻轻摇动即可同步结果";
      } else {
        desktopStatus("手机已断开", "error");
      }
    }
    if (message.type === "line_locked") renderDesktopLine(message.line);
    if (message.type === "cast_completed") showDesktopResult(message);
    if (message.type === "error") desktopStatus(message.message, "error");
  });
}

function lineGlyph(line) { return line.value % 2 === 0 ? "⚋" : "⚊"; }

function renderDesktopLine(line) {
  if (desktopState.lines.some(item => item.line_index === line.line_index)) return;
  desktopState.lines.push(line);
  desktopState.lines.sort((a, b) => a.line_index - b.line_index);
  desktopCoins.forEach((coin, index) => coin.classList.toggle("reverse", index >= line.fronts));
  desktopStage.classList.remove("resolving");
  void desktopStage.offsetWidth;
  desktopStage.classList.add("resolving");
  setTimeout(() => desktopStage.classList.remove("resolving"), 1150);

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
  source.textContent = "手机实时同步";
  detail.append(title, source);
  const position = document.createElement("span");
  position.className = "line-position";
  position.textContent = line.position_name;
  item.append(glyph, detail, position);
  $d("#desktopLineList").append(item);
  $d("#desktopLineCount").textContent = String(desktopState.lines.length);
  $d("#desktopHint").textContent = `${line.position_name}：${line.fronts}正${line.reverses}反 · ${line.line_type}`;
  $d("#desktopCompleteButton").disabled = desktopState.lines.length !== 6;
  desktopStatus(desktopState.lines.length === 6 ? "六爻已齐 · 等待排盘" : `已同步第 ${desktopState.lines.length} 爻`, "connected");
}

function completeOnDesktop() {
  if (desktopState.lines.length !== 6 || desktopState.busy || !desktopState.socket) return;
  desktopState.busy = true;
  $d("#desktopCompleteButton").disabled = true;
  desktopStatus("正在生成确定性盘面…");
  desktopState.socket.send(JSON.stringify({ type: "complete" }));
}

function showDesktopResult(message) {
  desktopState.busy = false;
  const summary = message.result_summary || {};
  $d("#desktopResult").hidden = false;
  $d("#desktopResultTitle").textContent = summary.changed_hexagram_name
    ? `${summary.hexagram_name || "本卦"} → ${summary.changed_hexagram_name}`
    : summary.hexagram_name || "排盘完成";
  $d("#desktopResultMeta").textContent = `Run ID · ${(message.run_id || "").slice(0, 8)} · ${summary.interpretation_status === "completed" ? "解读完成" : "确定性盘面已保留"}`;
  renderDesktopInterpretation($d("#desktopResultCopy"), summary.interpretation || "盘面已经生成。");
  desktopStatus("电脑与手机结果已统一", "connected");
  $d("#desktopResult").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

function renderDesktopInterpretation(container, text) {
  container.replaceChildren();
  String(text).split(/\n+/).map(line => line.trim()).filter(Boolean).forEach(line => {
    const heading = line.match(/^#{1,6}\s+(.+)$/);
    const element = document.createElement(heading ? "h3" : "p");
    element.textContent = (heading ? heading[1] : line).replace(/^\*\*(.+)\*\*$/, "$1");
    container.append(element);
  });
}

async function copyMobileLink() {
  if (!desktopState.mobileUrl) return;
  try {
    await navigator.clipboard.writeText(desktopState.mobileUrl);
    desktopStatus("手机链接已复制", "connected");
  } catch (_) {
    window.prompt("复制这个手机链接", desktopState.mobileUrl);
  }
}

$d("#createPairingButton").addEventListener("click", createPairing);
$d("#copyLinkButton").addEventListener("click", copyMobileLink);
$d("#desktopCompleteButton").addEventListener("click", completeOnDesktop);
