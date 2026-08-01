const { HISTORY_STORAGE_KEY } = require("../../utils/api");

function displayDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = number => String(number).padStart(2, "0");
  return `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())}`;
}

Page({
  data: { history: [] },

  onShow() {
    const history = wx.getStorageSync(HISTORY_STORAGE_KEY) || [];
    this.setData({
      history: history.map(item => ({ ...item, displayDate: displayDate(item.createdAt), expanded: false }))
    });
  },

  toggleItem(event) {
    const index = Number(event.currentTarget.dataset.index);
    const history = this.data.history.map((item, itemIndex) => ({
      ...item,
      expanded: itemIndex === index ? !item.expanded : item.expanded
    }));
    this.setData({ history });
  },

  clearHistory() {
    wx.showModal({
      title: "清空卦例",
      content: "仅删除这台手机内保存的历史结果，当前摇卦进度不受影响。",
      confirmColor: "#b8743c",
      success: result => {
        if (!result.confirm) return;
        wx.removeStorageSync(HISTORY_STORAGE_KEY);
        this.setData({ history: [] });
      }
    });
  }
});
