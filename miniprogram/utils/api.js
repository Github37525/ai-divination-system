const SESSION_STORAGE_KEY = "divination.active-session.v1";
const HISTORY_STORAGE_KEY = "divination.history.v1";

function apiBaseUrl() {
  return getApp().globalData.apiBaseUrl.replace(/\/$/, "");
}

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (options.token) headers.Authorization = `Bearer ${options.token}`;
    if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
    wx.request({
      url: `${apiBaseUrl()}${path}`,
      method: options.method || "GET",
      data: options.data,
      header: headers,
      timeout: 60000,
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data);
          return;
        }
        const detail = response.data && response.data.detail;
        const error = new Error(detail || `请求失败（${response.statusCode}）`);
        error.statusCode = response.statusCode;
        reject(error);
      },
      fail(error) {
        reject(new Error(error.errMsg || "网络连接失败，请稍后重试。"));
      }
    });
  });
}

function getConfig() {
  return request("/v1/config");
}

function createSession(question) {
  return request("/v1/cast-sessions", { method: "POST", data: { question } });
}

function getSession(sessionId, token) {
  return request(`/v1/cast-sessions/${sessionId}`, { token });
}

function lockLine(sessionId, token, triggerMode, motionEnergy, idempotencyKey) {
  return request(`/v1/cast-sessions/${sessionId}/lines`, {
    method: "POST",
    token,
    idempotencyKey,
    data: { trigger_mode: triggerMode, motion_energy: motionEnergy }
  });
}

function completeSession(sessionId, token) {
  return request(`/v1/cast-sessions/${sessionId}/complete`, {
    method: "POST",
    token
  });
}

function getResult(sessionId, token) {
  return request(`/v1/cast-sessions/${sessionId}/result`, { token });
}

module.exports = {
  SESSION_STORAGE_KEY,
  HISTORY_STORAGE_KEY,
  getConfig,
  createSession,
  getSession,
  lockLine,
  completeSession,
  getResult
};
