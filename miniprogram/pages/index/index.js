const api = require("../../utils/api");

const DEFAULT_CONFIG = {
  motion: {
    shake_threshold: 11.5,
    impulses_required: 3,
    window_ms: 900,
    cooldown_ms: 1400
  }
};

function idempotencyKey() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function decorateLine(line) {
  const labels = { motion: "体感触发", tap: "点按触发", paired: "手机协同" };
  return {
    ...line,
    glyph: line.value % 2 === 0 ? "⚋" : "⚊",
    sourceLabel: labels[line.trigger_mode] || "小程序触发"
  };
}

Page({
  data: {
    view: "setup",
    question: "",
    sessionId: "",
    sessionToken: "",
    lines: [],
    lineCount: 0,
    busy: false,
    resolving: false,
    motionEnabled: false,
    coins: [{ text: "乾" }, { text: "元" }, { text: "通" }],
    energyOpacity: .16,
    stageHint: "启用体感后轻轻摇动手机，或直接点按摇卦",
    status: "尚未开始",
    statusKind: "",
    pending: false,
    resultTitle: "",
    resultMeta: "",
    interpretation: ""
  },

  config: DEFAULT_CONFIG,
  pollTimer: null,
  lastVector: null,
  lastImpulseVector: null,
  impulses: [],
  directionChanges: 0,
  lastImpulseAt: 0,
  lastTriggerAt: 0,

  async onLoad() {
    this.accelerometerHandler = sample => this.handleAccelerometer(sample);
    try {
      this.config = await api.getConfig();
    } catch (_) {
      this.config = DEFAULT_CONFIG;
    }
    await this.restoreSession();
  },

  onHide() {
    this.stopMotion();
  },

  onUnload() {
    this.stopMotion();
    this.clearPollTimer();
  },

  onQuestionInput(event) {
    this.setData({ question: event.detail.value });
  },

  setStatus(status, statusKind = "") {
    this.setData({ status, statusKind });
  },

  async createCast() {
    const question = this.data.question.trim();
    if (!question) {
      this.showError("请先写下本次占问事项。");
      return;
    }
    this.setData({ busy: true });
    this.setStatus("正在创建安全会话…");
    try {
      const session = await api.createSession(question);
      wx.setStorageSync(api.SESSION_STORAGE_KEY, {
        sessionId: session.session_id,
        sessionToken: session.session_token,
        question
      });
      this.setData({
        view: "cast",
        busy: false,
        sessionId: session.session_id,
        sessionToken: session.session_token,
        lines: [],
        lineCount: 0
      });
      this.setStatus("会话已建立 · 可以开始摇卦", "connected");
    } catch (error) {
      this.setData({ busy: false });
      this.showError(error.message);
    }
  },

  async restoreSession() {
    const saved = wx.getStorageSync(api.SESSION_STORAGE_KEY);
    if (!saved || !saved.sessionId || !saved.sessionToken) return;
    this.setStatus("正在恢复上次进度…");
    try {
      const session = await api.getSession(saved.sessionId, saved.sessionToken);
      const lines = (session.lines || []).map(decorateLine);
      this.setData({
        view: "cast",
        question: saved.question || "",
        sessionId: saved.sessionId,
        sessionToken: saved.sessionToken,
        lines,
        lineCount: lines.length
      });
      if (["interpretation_pending", "interpreting", "completed", "interpretation_failed"].includes(session.status)) {
        await this.refreshResult();
      } else {
        this.setStatus(`已恢复 · ${lines.length} / 6 爻`, "connected");
      }
    } catch (_) {
      wx.removeStorageSync(api.SESSION_STORAGE_KEY);
      this.setStatus("上次会话已过期，请重新起卦。");
    }
  },

  tapCast() {
    this.triggerLine("tap", null);
  },

  async triggerLine(triggerMode, motionEnergy) {
    if (this.data.busy || this.data.lineCount >= 6 || !this.data.sessionId) return;
    this.setData({ busy: true, resolving: true, stageHint: "铜钱正在落定…" });
    try {
      const payload = await api.lockLine(
        this.data.sessionId,
        this.data.sessionToken,
        triggerMode,
        motionEnergy,
        idempotencyKey()
      );
      const line = decorateLine(payload.line);
      const lines = [...this.data.lines.filter(item => item.line_index !== line.line_index), line]
        .sort((a, b) => a.line_index - b.line_index);
      const coins = [0, 1, 2].map(index => ({
        text: index === 0 ? "乾" : index === 1 ? "元" : "通",
        reverse: index >= line.fronts
      }));
      this.setData({
        lines,
        lineCount: lines.length,
        coins,
        stageHint: `${line.position_name}：${line.fronts}正${line.reverses}反 · ${line.line_type}`
      });
      this.vibrateLine(line.moving);
      this.setStatus(`第 ${lines.length} 爻已落定`, "connected");
      setTimeout(() => this.setData({ busy: false, resolving: false }), 900);
    } catch (error) {
      this.setData({ busy: false, resolving: false });
      this.showError(error.message);
    }
  },

  vibrateLine(moving) {
    wx.vibrateShort({ type: moving ? "heavy" : "medium", fail() {} });
  },

  toggleMotion() {
    if (this.data.motionEnabled) {
      this.stopMotion();
      this.setStatus("体感已关闭，可继续点按摇卦。");
      return;
    }
    wx.startAccelerometer({
      interval: "game",
      success: () => {
        this.resetMotionState();
        wx.onAccelerometerChange(this.accelerometerHandler);
        this.setData({ motionEnabled: true, stageHint: "连续轻摇，达到阈值后自动生成一爻" });
        this.setStatus("体感已启用 · 请握稳手机", "connected");
      },
      fail: () => this.showError("无法启用运动传感器，请使用点按摇卦。")
    });
  },

  handleAccelerometer: function handleAccelerometer(sample) {
    if (!this.data.motionEnabled || this.data.busy || this.data.lineCount >= 6) return;
    const now = Date.now();
    const current = [sample.x, sample.y, sample.z];
    const previous = this.lastVector;
    this.lastVector = current;
    if (!previous) return;
    const vector = current.map((value, index) => (value - previous[index]) * 9.80665);
    const energy = Math.hypot(...vector);
    const cfg = this.config.motion || DEFAULT_CONFIG.motion;
    this.setData({ energyOpacity: Math.min(1, .16 + energy / cfg.shake_threshold * .84) });
    if (energy < cfg.shake_threshold || now - this.lastImpulseAt < 120) return;
    this.lastImpulseAt = now;
    if (this.changedDirection(this.lastImpulseVector, vector)) this.directionChanges += 1;
    this.lastImpulseVector = vector;
    this.impulses.push(now);
    this.impulses = this.impulses.filter(time => now - time <= cfg.window_ms);
    if (
      this.impulses.length >= cfg.impulses_required &&
      this.directionChanges >= 1 &&
      this.impulses[this.impulses.length - 1] - this.impulses[0] >= 240 &&
      now - this.lastTriggerAt >= cfg.cooldown_ms
    ) {
      this.lastTriggerAt = now;
      this.impulses = [];
      this.directionChanges = 0;
      this.lastImpulseVector = null;
      this.triggerLine("motion", Math.min(100, Math.round(energy / cfg.shake_threshold * 55)));
    }
  },

  changedDirection(previous, current) {
    if (!previous || !current) return false;
    const denominator = Math.hypot(...previous) * Math.hypot(...current);
    if (!denominator) return false;
    const cosine = previous.reduce((sum, value, index) => sum + value * current[index], 0) / denominator;
    return cosine < .55;
  },

  resetMotionState() {
    this.lastVector = null;
    this.lastImpulseVector = null;
    this.impulses = [];
    this.directionChanges = 0;
    this.lastImpulseAt = 0;
  },

  stopMotion() {
    if (this.accelerometerHandler) {
      wx.offAccelerometerChange(this.accelerometerHandler);
    }
    wx.stopAccelerometer({ fail() {} });
    if (this.data.motionEnabled) this.setData({ motionEnabled: false, energyOpacity: .16 });
  },

  async completeCast() {
    if (this.data.lineCount !== 6 || this.data.busy) return;
    this.stopMotion();
    this.setData({ busy: true });
    this.setStatus("正在生成确定性盘面…");
    try {
      const result = await api.completeSession(this.data.sessionId, this.data.sessionToken);
      this.presentResult(result);
      if (["interpretation_pending", "interpreting"].includes(result.status)) this.schedulePoll();
    } catch (error) {
      this.setData({ busy: false });
      this.showError(error.message);
    }
  },

  async refreshResult() {
    if (!this.data.sessionId) return;
    try {
      const result = await api.getResult(this.data.sessionId, this.data.sessionToken);
      this.presentResult(result);
      if (["interpretation_pending", "interpreting"].includes(result.status)) this.schedulePoll();
    } catch (error) {
      this.showError(error.message);
    }
  },

  schedulePoll() {
    this.clearPollTimer();
    this.pollTimer = setTimeout(() => this.refreshResult(), 1400);
  },

  clearPollTimer() {
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.pollTimer = null;
  },

  presentResult(payload) {
    const summary = payload.result_summary || {};
    const pending = ["interpretation_pending", "interpreting"].includes(payload.status);
    const title = summary.changed_hexagram_name
      ? `${summary.hexagram_name || "本卦"} → ${summary.changed_hexagram_name}`
      : summary.hexagram_name || "盘面已完成";
    const interpretation = summary.interpretation || "确定性盘面已完成，DeepSeek 正在后台生成白话解读。";
    const label = pending
      ? "DeepSeek 解读生成中"
      : summary.ai_generated && summary.interpretation_mode === "api"
        ? "DeepSeek 解读完成"
        : "规则解读已完成";
    this.setData({
      view: "result",
      busy: false,
      pending,
      resultTitle: title,
      resultMeta: `Run ID · ${(payload.run_id || "").slice(0, 8)} · ${label}`,
      interpretation
    });
    this.setStatus(pending ? "盘面完成 · 解读生成中" : "六爻完成", "connected");
    if (!pending) {
      this.clearPollTimer();
      wx.vibrateLong({ fail() {} });
      this.saveHistory(payload, title, interpretation);
    }
  },

  saveHistory(payload, title, interpretation) {
    const history = wx.getStorageSync(api.HISTORY_STORAGE_KEY) || [];
    if (history.some(item => item.runId === payload.run_id)) return;
    history.unshift({
      runId: payload.run_id,
      title,
      question: this.data.question,
      interpretation,
      createdAt: new Date().toISOString()
    });
    wx.setStorageSync(api.HISTORY_STORAGE_KEY, history.slice(0, 20));
  },

  newCast() {
    this.clearPollTimer();
    wx.removeStorageSync(api.SESSION_STORAGE_KEY);
    this.setData({
      view: "setup",
      question: "",
      sessionId: "",
      sessionToken: "",
      lines: [],
      lineCount: 0,
      pending: false,
      interpretation: "",
      coins: [{ text: "乾" }, { text: "元" }, { text: "通" }]
    });
    this.setStatus("尚未开始");
  },

  showError(message) {
    this.setStatus(message || "发生错误，请稍后重试。", "error");
    wx.showToast({ title: message || "请求失败", icon: "none", duration: 2600 });
  }
});
