const { HEXAGRAMS } = require("../../data/hexagrams");

Page({
  data: {
    query: "",
    hexagrams: HEXAGRAMS,
    filteredCount: HEXAGRAMS.length
  },

  onSearch(event) {
    const query = event.detail.value.trim().toLowerCase();
    const hexagrams = query
      ? HEXAGRAMS.filter(item => item.keywords.toLowerCase().includes(query))
      : HEXAGRAMS;
    this.setData({ query: event.detail.value, hexagrams, filteredCount: hexagrams.length });
  },

  clearSearch() {
    this.setData({ query: "", hexagrams: HEXAGRAMS, filteredCount: HEXAGRAMS.length });
  }
});
