const terms = [
      {
        title: "阴阳与爻",
        description: "每一卦由六条爻组成。连续的一画称阳爻，中间断开的两段称阴爻。页面中的六爻均按经典习惯由下向上排列。"
      },
      {
        title: "八卦与重卦",
        description: "三爻构成一个经卦，即乾、坤、震、巽、坎、离、艮、兑。上下两个经卦相重，形成六爻的别卦，共六十四种。"
      },
      {
        title: "卦辞",
        description: "卦辞位于一卦之首，是该卦的核心经文。研读时宜结合卦名、上下卦结构及后续传文理解。"
      },
      {
        title: "彖传",
        description: "彖传是对卦名、卦辞和卦体关系的阐释。本应用把彖传与卦辞分区呈现，便于对读。"
      },
      {
        title: "象传",
        description: "大象解释一卦整体取象，小象分别解释六条爻辞。详情页中的“《象》曰”对应各爻的小象传。"
      },
      {
        title: "爻位名称",
        description: "六爻从下至上依次称初、二、三、四、五、上；阳爻以“九”表示，阴爻以“六”表示，如初九、六二、上六。"
      }
];

Page({
  data: {
    terms: terms.map((item, index) => ({
      ...item,
      indexLabel: String(index + 1).padStart(2, "0")
    }))
  }
});
