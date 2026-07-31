"""从维基文库 API 构建可追溯的六十四卦规则数据库。

正文只取《周易》公版原文；八宫、世应、纳甲、五行与六亲均由固定规则生成。
运行：py -3 scripts/build_hexagrams_db.py
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "hexagrams_db.json"
META_PATH = ROOT / "data" / "hexagrams_db.meta.json"
EXPORT_URL = "https://zh.wikisource.org/wiki/Special:Export"
USER_AGENT = "divination-engine/2.0 (classical text database builder)"

KING_WEN_NAMES = (
    "乾", "坤", "屯", "蒙", "需", "訟", "師", "比", "小畜", "履", "泰", "否",
    "同人", "大有", "謙", "豫", "隨", "蠱", "臨", "觀", "噬嗑", "賁", "剝", "復",
    "无妄", "大畜", "頤", "大過", "坎", "離", "咸", "恒", "遯", "大壯", "晉", "明夷",
    "家人", "睽", "蹇", "解", "損", "益", "夬", "姤", "萃", "升", "困", "井",
    "革", "鼎", "震", "艮", "漸", "歸妹", "豐", "旅", "巽", "兌", "渙", "節",
    "中孚", "小過", "既濟", "未濟",
)

SIMPLIFIED_NAMES = (
    "乾", "坤", "屯", "蒙", "需", "讼", "师", "比", "小畜", "履", "泰", "否",
    "同人", "大有", "谦", "豫", "随", "蛊", "临", "观", "噬嗑", "贲", "剥", "复",
    "无妄", "大畜", "颐", "大过", "坎", "离", "咸", "恒", "遁", "大壮", "晋", "明夷",
    "家人", "睽", "蹇", "解", "损", "益", "夬", "姤", "萃", "升", "困", "井",
    "革", "鼎", "震", "艮", "渐", "归妹", "丰", "旅", "巽", "兑", "涣", "节",
    "中孚", "小过", "既济", "未济",
)

CTEXT_SLUGS = (
    "qian", "kun", "zhun", "meng", "xu", "song", "shi", "bi", "xiao-xu", "lu", "tai", "pi",
    "tong-ren", "da-you", "qian1", "yu", "sui", "gu", "lin", "guan", "shi-he", "bi1", "bo", "fu",
    "wu-wang", "da-xu", "yi", "da-guo", "kan", "li", "xian", "heng", "dun", "da-zhuang", "jin", "ming-yi",
    "jia-ren", "kui", "jian", "jie", "sun", "yi1", "guai", "gou", "cui", "sheng", "kun1", "jing",
    "ge", "ding", "zhen", "gen", "jian1", "gui-mei", "feng", "lu1", "xun", "dui", "huan", "jie1",
    "zhong-fu", "xiao-guo", "ji-ji", "wei-ji",
)

TRIGRAM_BITS = {
    "乾": "111", "兌": "110", "離": "101", "震": "100",
    "巽": "011", "坎": "010", "艮": "001", "坤": "000",
}
TRIGRAM_SIMPLE = {
    "乾": "乾", "兌": "兑", "離": "离", "震": "震",
    "巽": "巽", "坎": "坎", "艮": "艮", "坤": "坤",
}
TRIGRAM_IMAGES = {
    "乾": ("天", "天"), "兌": ("澤", "泽"), "離": ("火", "火"), "震": ("雷", "雷"),
    "巽": ("風", "风"), "坎": ("水", "水"), "艮": ("山", "山"), "坤": ("地", "地"),
}
PALACE_ELEMENTS = {
    "乾": "金", "兌": "金", "離": "火", "震": "木",
    "巽": "木", "坎": "水", "艮": "土", "坤": "土",
}
BRANCH_ELEMENTS = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}
NAJIA = {
    "乾": ("甲", "子寅辰", "壬", "午申戌"),
    "坎": ("戊", "寅辰午", "戊", "申戌子"),
    "艮": ("丙", "辰午申", "丙", "戌子寅"),
    "震": ("庚", "子寅辰", "庚", "午申戌"),
    "巽": ("辛", "丑亥酉", "辛", "未巳卯"),
    "離": ("己", "卯丑亥", "己", "酉未巳"),
    "坤": ("乙", "未巳卯", "癸", "丑亥酉"),
    "兌": ("丁", "巳卯丑", "丁", "亥酉未"),
}
GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
PALACE_SEQUENCE = (
    (frozenset(), 6, 3, "本宫"),
    (frozenset({0}), 1, 4, "一世"),
    (frozenset({0, 1}), 2, 5, "二世"),
    (frozenset({0, 1, 2}), 3, 6, "三世"),
    (frozenset({0, 1, 2, 3}), 4, 1, "四世"),
    (frozenset({0, 1, 2, 3, 4}), 5, 2, "五世"),
    (frozenset({0, 1, 2, 4}), 4, 1, "游魂"),
    (frozenset({4}), 3, 6, "归魂"),
)
LINE_PATTERN = re.compile(r"^(初[六九]|[六九][二三四五]|上[六九]|用[六九])[：，](.+)$")
TRIGRAM_PATTERN = re.compile(r"([乾兌離震巽坎艮坤])下([乾兌離震巽坎艮坤])上")


def _fetch_pages() -> dict[str, dict[str, Any]]:
    """用一次 Special:Export 请求取得 64 页，避免逐页请求触发限流。"""
    titles = [f"周易/{name}" for name in KING_WEN_NAMES]
    body = urlencode({"pages": "\n".join(titles), "curonly": "1"}).encode("utf-8")
    request = Request(
        EXPORT_URL,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
    )
    with urlopen(request, timeout=90) as response:
        root = ElementTree.fromstring(response.read())

    namespace = {"mw": root.tag.split("}", 1)[0].lstrip("{")}
    pages: dict[str, dict[str, Any]] = {}
    for page_node in root.findall("mw:page", namespace):
        title = page_node.findtext("mw:title", namespaces=namespace)
        revision = page_node.find("mw:revision", namespace)
        if not title or revision is None:
            continue
        text_node = revision.find("mw:text", namespace)
        pages[title] = {
            "title": title,
            "wikitext": text_node.text if text_node is not None and text_node.text else "",
            "revision_id": int(revision.findtext("mw:id", default="0", namespaces=namespace)),
            "revision_timestamp": revision.findtext("mw:timestamp", default="", namespaces=namespace),
        }

    missing = sorted(set(titles) - set(pages))
    if missing:
        raise RuntimeError(f"Special:Export 缺少页面：{missing}")
    return pages


def _plain_wikitext(line: str) -> str:
    """去除本数据所见的展示标记，保留正文和异文注记。"""
    value = line.strip()
    value = re.sub(r"^[-*#:;]+", "", value)
    value = re.sub(r"-\{([^{}]+)\}-", r"\1", value)
    value = re.sub(r"\{\{\*\|([^{}]+)\}\}", r"（\1）", value)
    value = re.sub(r"\[\[File:[^\]]+\]\]", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("'''", "").replace("''", "")
    return html.unescape(value).strip()


def _build_palace_table() -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for palace, trigram_bits in TRIGRAM_BITS.items():
        base = trigram_bits + trigram_bits
        for flips, shi, ying, position in PALACE_SEQUENCE:
            code = "".join(
                str(1 - int(bit)) if index in flips else bit
                for index, bit in enumerate(base)
            )
            if code in table:
                raise RuntimeError(f"八宫规则生成重复卦码：{code}")
            table[code] = {
                "palace_name": TRIGRAM_SIMPLE[palace],
                "palace_name_canonical": palace,
                "palace_element": PALACE_ELEMENTS[palace],
                "palace_position": position,
                "shi": shi,
                "ying": ying,
            }
    if len(table) != 64:
        raise RuntimeError(f"八宫规则应覆盖64卦，实际 {len(table)}")
    return table


def _six_relative(line_element: str, palace_element: str) -> str:
    if line_element == palace_element:
        return "兄弟"
    if GENERATES[line_element] == palace_element:
        return "父母"
    if GENERATES[palace_element] == line_element:
        return "子孙"
    if CONTROLS[line_element] == palace_element:
        return "官鬼"
    return "妻财"


def _full_name(
    simple_name: str,
    canonical_name: str,
    lower: str,
    upper: str,
) -> tuple[str, str]:
    if lower == upper:
        return (
            f"{simple_name}为{TRIGRAM_IMAGES[upper][1]}",
            f"{canonical_name}為{TRIGRAM_IMAGES[upper][0]}",
        )
    return (
        f"{TRIGRAM_IMAGES[upper][1]}{TRIGRAM_IMAGES[lower][1]}{simple_name}",
        f"{TRIGRAM_IMAGES[upper][0]}{TRIGRAM_IMAGES[lower][0]}{canonical_name}",
    )


def _parse_page(
    page: dict[str, Any],
    number: int,
    simple_name: str,
    ctext_slug: str,
    palace_table: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    source_title = page["title"]
    canonical_name = source_title.split("/", 1)[1]
    marked_lines = [
        (line.strip(), _plain_wikitext(line))
        for line in page["wikitext"].splitlines()
        if _plain_wikitext(line)
    ]
    raw_lines = [plain for _, plain in marked_lines]
    try:
        classic_start = next(
            index for index, line in enumerate(raw_lines) if line.endswith("易經：")
        ) + 1
        tuan_start = next(
            index for index, line in enumerate(raw_lines) if line == "彖曰："
        )
        image_start = next(
            index for index, line in enumerate(raw_lines) if line == "象曰："
        )
    except StopIteration as error:
        raise RuntimeError(f"{source_title} 的章节结构无法识别") from error

    trigram_match = next((TRIGRAM_PATTERN.search(line) for line in raw_lines[:classic_start] if TRIGRAM_PATTERN.search(line)), None)
    if not trigram_match:
        raise RuntimeError(f"{source_title} 缺少上下卦信息")
    lower, upper = trigram_match.groups()
    code = TRIGRAM_BITS[lower] + TRIGRAM_BITS[upper]

    classic_lines = raw_lines[classic_start:tuan_start]
    parsed_lines = []
    judgement_parts = []
    for line in classic_lines:
        match = LINE_PATTERN.match(line)
        if match:
            parsed_lines.append({"line_name": match.group(1), "text": match.group(2)})
        elif not parsed_lines:
            judgement_parts.append(line)
        else:
            parsed_lines[-1]["text"] += line
    if judgement_parts and judgement_parts[0].startswith(f"{canonical_name}："):
        judgement_parts[0] = judgement_parts[0].split("：", 1)[1]

    standard_lines = [item for item in parsed_lines if not item["line_name"].startswith("用")]
    special_lines = [item for item in parsed_lines if item["line_name"].startswith("用")]
    if len(standard_lines) != 6 or len(special_lines) > 1:
        raise RuntimeError(
            f"{source_title} 爻辞数量异常：标准 {len(standard_lines)}，特殊 {len(special_lines)}"
        )

    image_end = next(
        (
            index
            for index in range(image_start + 1, len(raw_lines))
            if raw_lines[index].endswith("曰：")
        ),
        len(raw_lines),
    )
    image_lines = raw_lines[image_start + 1:image_end]
    expected_images = 1 + len(parsed_lines)
    if len(image_lines) != expected_images:
        raise RuntimeError(
            f"{source_title} 象辞数量异常：预期 {expected_images}，实际 {len(image_lines)}"
        )

    rule = palace_table[code]
    inner_stem, inner_branches, _, _ = NAJIA[lower]
    _, _, outer_stem, outer_branches = NAJIA[upper]
    stems = [inner_stem] * 3 + [outer_stem] * 3
    branches = list(inner_branches + outer_branches)

    lines_detail: dict[str, dict[str, Any]] = {}
    najia_values = []
    for index, line in enumerate(standard_lines, start=1):
        branch = branches[index - 1]
        stem = stems[index - 1]
        element = BRANCH_ELEMENTS[branch]
        najia = f"{stem}{branch}"
        najia_values.append(najia)
        lines_detail[str(index)] = {
            **line,
            "image": image_lines[index],
            "yin_yang": "阳" if code[index - 1] == "1" else "阴",
            "najia": najia,
            "stem": stem,
            "branch": branch,
            "element": element,
            "relative": _six_relative(element, rule["palace_element"]),
            "is_shi": index == rule["shi"],
            "is_ying": index == rule["ying"],
        }

    display_name, source_name = _full_name(simple_name, canonical_name, lower, upper)
    special_line = None
    if special_lines:
        special_line = {**special_lines[0], "image": image_lines[-1]}

    return code, {
        "king_wen_number": number,
        "symbol": chr(0x4DC0 + number - 1),
        "name": display_name,
        "canonical_name": source_name,
        "lower_trigram": TRIGRAM_SIMPLE[lower],
        "upper_trigram": TRIGRAM_SIMPLE[upper],
        "lower_trigram_canonical": lower,
        "upper_trigram_canonical": upper,
        "palace": f"{rule['palace_name']}{rule['palace_element']}",
        **rule,
        "judgement": "\n".join(judgement_parts),
        "tuan": "\n".join(raw_lines[tuan_start + 1:image_start]),
        "image": image_lines[0],
        "shi": rule["shi"],
        "ying": rule["ying"],
        "najia": najia_values,
        "lines": lines_detail,
        "special_line": special_line,
        "source": {
            "title": source_title,
            "url": f"https://zh.wikisource.org/wiki/{source_title}",
            "revision_id": page["revision_id"],
            "revision_timestamp": page["revision_timestamp"],
            "text_variant": "traditional",
            "verification_url": f"https://ctext.org/book-of-changes/{ctext_slug}/zhs",
        },
    }


def build_database() -> dict[str, dict[str, Any]]:
    pages = _fetch_pages()
    palace_table = _build_palace_table()
    database: dict[str, dict[str, Any]] = {}
    for number, (canonical, simplified, ctext_slug) in enumerate(
        zip(KING_WEN_NAMES, SIMPLIFIED_NAMES, CTEXT_SLUGS),
        start=1,
    ):
        title = f"周易/{canonical}"
        code, record = _parse_page(
            pages[title], number, simplified, ctext_slug, palace_table
        )
        if code in database:
            raise RuntimeError(f"卦码 {code} 被重复使用：{record['name']}")
        database[code] = record

    if set(database) != set(palace_table):
        missing = sorted(set(palace_table) - set(database))
        extra = sorted(set(database) - set(palace_table))
        raise RuntimeError(f"64卦覆盖不完整，缺少 {missing}，多出 {extra}")
    return database


def main() -> None:
    database = build_database()
    serialized = json.dumps(database, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    database_bytes = serialized.encode("utf-8")
    DB_PATH.write_bytes(database_bytes)
    metadata = {
        "schema_version": "2.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(database),
        "sha256": hashlib.sha256(database_bytes).hexdigest(),
        "primary_source": {
            "name": "Chinese Wikisource 周易/卦名 pages",
            "url": "https://zh.wikisource.org/wiki/周易",
            "fetch_method": "single POST to Special:Export with 64 page titles",
            "work_status": "public domain; page revision attribution retained per record",
        },
        "verification_sources": [
            "https://ctext.org/book-of-changes/yi-jing/zhs",
            "https://zh.wikisource.org/wiki/周易#分宮卦象次序表",
            "https://github.com/yaomancy/liuyao-engine",
        ],
        "rule_sources": [
            "京房八宫卦变规则",
            "纳甲歌诀：乾金甲子外壬午等八卦纳甲表",
        ],
        "validation": {
            "hexagrams": 64,
            "standard_lines": 384,
            "special_lines": 2,
            "palace_records_per_palace": 8,
        },
    }
    META_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"generated {len(database)} records -> {DB_PATH}")
    print(f"sha256={metadata['sha256']}")


if __name__ == "__main__":
    main()
