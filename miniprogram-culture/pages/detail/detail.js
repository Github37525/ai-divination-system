const { HEXAGRAMS } = require("../../data/hexagrams");

Page({
  data: { record: null },

  onLoad(options) {
    const record = HEXAGRAMS.find(item => item.code === options.code) || null;
    this.setData({ record });
    if (record) wx.setNavigationBarTitle({ title: `第${record.number}卦 · ${record.name}` });
  }
});
