"""时家转盘奇门（拆补法）与出生盘的确定性结构计算。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import sxtwl

from .astronomy import AstronomyService, JIEQI_NAMES
from .config import DIZHI, FIVE_ELEMENTS, TIANGAN


class QimenCalculationError(ValueError):
    """奇门输入或机械排盘规则无法完成。"""


JIAZI = [f"{TIANGAN[index % 10]}{DIZHI[index % 12]}" for index in range(60)]
SANQI_LIUYI = ("戊", "己", "庚", "辛", "壬", "癸", "丁", "丙", "乙")
XUN_HIDDEN_STEM = {
    "甲子": "戊", "甲戌": "己", "甲申": "庚",
    "甲午": "辛", "甲辰": "壬", "甲寅": "癸",
}
XUN_VOID = {
    "甲子": ("戌", "亥"), "甲戌": ("申", "酉"), "甲申": ("午", "未"),
    "甲午": ("辰", "巳"), "甲辰": ("寅", "卯"), "甲寅": ("子", "丑"),
}
JU_TABLE = {
    "冬至": (1, 7, 4), "小寒": (2, 8, 5), "大寒": (3, 9, 6),
    "立春": (8, 5, 2), "雨水": (9, 6, 3), "惊蛰": (1, 7, 4),
    "春分": (3, 9, 6), "清明": (4, 1, 7), "谷雨": (5, 2, 8),
    "立夏": (4, 1, 7), "小满": (5, 2, 8), "芒种": (6, 3, 9),
    "夏至": (9, 3, 6), "小暑": (8, 2, 5), "大暑": (7, 1, 4),
    "立秋": (2, 5, 8), "处暑": (1, 4, 7), "白露": (9, 3, 6),
    "秋分": (7, 1, 4), "寒露": (6, 9, 3), "霜降": (5, 8, 2),
    "立冬": (6, 9, 3), "小雪": (5, 8, 2), "大雪": (4, 7, 1),
}
YANG_TERMS = frozenset(tuple(JIEQI_NAMES[:12]))
PALACE_NAMES = {1: "坎", 2: "坤", 3: "震", 4: "巽", 5: "中", 6: "乾", 7: "兑", 8: "艮", 9: "离"}
PALACE_BRANCHES = {
    1: ("子",), 2: ("未", "申"), 3: ("卯",), 4: ("辰", "巳"),
    5: (), 6: ("戌", "亥"), 7: ("酉",), 8: ("丑", "寅"), 9: ("午",),
}
PALACE_ELEMENTS = {1: "水", 2: "土", 3: "木", 4: "木", 5: "土", 6: "金", 7: "金", 8: "土", 9: "火"}
STAR_BY_PALACE = {1: "天蓬", 2: "天芮", 3: "天冲", 4: "天辅", 5: "天禽", 6: "天心", 7: "天柱", 8: "天任", 9: "天英"}
GATE_BY_PALACE = {1: "休门", 2: "死门", 3: "伤门", 4: "杜门", 6: "开门", 7: "惊门", 8: "生门", 9: "景门"}
STAR_SEQUENCE = ("天心", "天蓬", "天任", "天冲", "天辅", "天英", "天芮", "天柱")
GATE_SEQUENCE = ("休门", "生门", "伤门", "杜门", "景门", "死门", "惊门", "开门")
PALACE_CLOCKWISE = (2, 7, 6, 1, 8, 3, 4, 9)
PALACE_COUNTER_CLOCKWISE = tuple(reversed(PALACE_CLOCKWISE))
DEITIES = ("值符", "腾蛇", "太阴", "六合", "白虎", "玄武", "九地", "九天")
STEM_ELEMENTS = {stem: element for stem, element in zip(TIANGAN, ("木", "木", "火", "火", "土", "土", "金", "金", "水", "水"))}


def _wrap_palace(value: int) -> int:
    return (value - 1) % 9 + 1


def _xun_head(ganzhi: str) -> str:
    try:
        return JIAZI[(JIAZI.index(ganzhi) // 10) * 10]
    except ValueError as error:
        raise QimenCalculationError(f"非法时柱干支：{ganzhi}") from error


class QimenService:
    """只计算公开、可验证的拆补转盘结构，不生成吉凶断语。"""

    @staticmethod
    def _earth_plate(ju: int, is_yang: bool) -> Dict[int, str]:
        direction = 1 if is_yang else -1
        return {_wrap_palace(ju + index * direction): stem for index, stem in enumerate(SANQI_LIUYI)}

    @staticmethod
    def _yuan(day_ganzhi: str) -> tuple[int, str]:
        try:
            value = JIAZI.index(day_ganzhi) % 15 // 5
        except ValueError as error:
            raise QimenCalculationError(f"非法日柱干支：{day_ganzhi}") from error
        return value, ("上元", "中元", "下元")[value]

    @staticmethod
    def build_asking_chart(
        dt: datetime,
        longitude: float = 120.0,
        latitude: Optional[float] = None,
        timezone_offset_hours: float = 8.0,
        category: str = "综合",
    ) -> Dict[str, Any]:
        calendar = AstronomyService.get_ganzhi_calendar(
            dt, longitude, latitude, timezone_offset_hours
        )
        term = calendar["current_solar_term"]["name"]
        if term not in JU_TABLE:
            raise QimenCalculationError(f"节气 {term} 缺少定局表。")
        yuan_index, yuan_name = QimenService._yuan(calendar["day_ganzhi"])
        is_yang = term in YANG_TERMS
        ju = JU_TABLE[term][yuan_index]
        earth = QimenService._earth_plate(ju, is_yang)
        hour_ganzhi = calendar["hour_ganzhi"]
        xun_head = _xun_head(hour_ganzhi)
        hidden_stem = XUN_HIDDEN_STEM[xun_head]
        zhi_fu_origin = next(position for position, stem in earth.items() if stem == hidden_stem)
        zhi_fu_star = STAR_BY_PALACE[zhi_fu_origin]
        actual_hour_stem = hidden_stem if hour_ganzhi[0] == "甲" else hour_ganzhi[0]
        zhi_fu_landing = next(position for position, stem in earth.items() if stem == actual_hour_stem)
        if zhi_fu_landing == 5:
            zhi_fu_landing = 2

        effective_star = "天芮" if zhi_fu_star == "天禽" else zhi_fu_star
        star_start = STAR_SEQUENCE.index(effective_star)
        palace_start = PALACE_CLOCKWISE.index(zhi_fu_landing)
        heaven: Dict[int, str] = {}
        stars: Dict[int, List[str]] = {}
        for step in range(8):
            position = PALACE_CLOCKWISE[(palace_start + step) % 8]
            star = STAR_SEQUENCE[(star_start + step) % 8]
            origin = next(key for key, value in STAR_BY_PALACE.items() if value == star)
            heaven[position] = earth[origin]
            stars[position] = [star]
        heaven[5] = earth[5]
        stars[5] = ["天禽"]
        tianrui_position = next(position for position, value in stars.items() if "天芮" in value)
        if tianrui_position != 5:
            stars[tianrui_position].append("天禽")

        zhi_shi_gate = GATE_BY_PALACE[2 if zhi_fu_origin == 5 else zhi_fu_origin]
        xun_branch_index = DIZHI.index(xun_head[1])
        hour_branch_index = DIZHI.index(hour_ganzhi[1])
        steps = (hour_branch_index - xun_branch_index) % 12
        raw_gate_position = _wrap_palace(zhi_fu_origin + steps * (1 if is_yang else -1))
        zhi_shi_landing = (8 if is_yang else 2) if raw_gate_position == 5 else raw_gate_position
        gate_start = GATE_SEQUENCE.index(zhi_shi_gate)
        gate_palace_start = PALACE_CLOCKWISE.index(zhi_shi_landing)
        gates = {
            PALACE_CLOCKWISE[(gate_palace_start + step) % 8]: GATE_SEQUENCE[(gate_start + step) % 8]
            for step in range(8)
        }
        deity_path = PALACE_CLOCKWISE if is_yang else PALACE_COUNTER_CLOCKWISE
        deity_start = deity_path.index(zhi_fu_landing)
        deities = {
            deity_path[(deity_start + step) % 8]: deity
            for step, deity in enumerate(DEITIES)
        }
        void_branches = XUN_VOID[xun_head]
        palaces = []
        for position in range(1, 10):
            earth_stems = [earth[position]]
            if position == (8 if is_yang else 2):
                earth_stems.append(earth[5])
            heaven_stems = [heaven[position]]
            if position == tianrui_position and position != 5:
                heaven_stems.append(earth[5])
            palaces.append(
                {
                    "position": position,
                    "name": PALACE_NAMES[position],
                    "element": PALACE_ELEMENTS[position],
                    "branches": list(PALACE_BRANCHES[position]),
                    "earth_stems": earth_stems,
                    "heaven_stems": heaven_stems,
                    "stars": stars[position],
                    "gate": gates.get(position),
                    "deity": deities.get(position),
                    "is_void": bool(set(PALACE_BRANCHES[position]) & set(void_branches)),
                }
            )
        return {
            "chart_type": "问事奇门",
            "category": category.strip() or "综合",
            "school": "时家转盘奇门",
            "ju_method": "拆补法（以日干支符头定上中下元）",
            "middle_palace_rule": "阳遁寄艮八，阴遁寄坤二；天禽随天芮",
            "calendar": calendar,
            "solar_term": term,
            "yuan": yuan_name,
            "dun": "阳遁" if is_yang else "阴遁",
            "ju_number": ju,
            "xun_head": xun_head,
            "hidden_stem": hidden_stem,
            "void_branches": list(void_branches),
            "zhi_fu": {"star": zhi_fu_star, "origin_palace": zhi_fu_origin, "position": zhi_fu_landing},
            "zhi_shi": {"gate": zhi_shi_gate, "position": zhi_shi_landing},
            "palaces": palaces,
        }

    @staticmethod
    def _month_terms_around(reference: datetime) -> tuple[dict, dict]:
        events = []
        for delta in range(-45, 46):
            event = AstronomyService._term_on_day((reference + timedelta(days=delta)).date())
            if event and event["index"] % 2 == 1:
                events.append(event)
        events.sort(key=lambda value: value["time"])
        previous = next((value for value in reversed(events) if value["time"] <= reference), None)
        following = next((value for value in events if value["time"] > reference), None)
        if not previous or not following:
            raise QimenCalculationError("无法定位出生时刻前后的节令。")
        return previous, following

    @staticmethod
    def build_lifelong_chart(
        birth_dt: datetime,
        longitude: float,
        latitude: float,
        gender: str,
        flow_year: Optional[int] = None,
        timezone_offset_hours: float = 8.0,
    ) -> Dict[str, Any]:
        if gender not in {"男", "女"}:
            raise QimenCalculationError("性别必须是“男”或“女”，用于确定大运顺逆。")
        birth_chart = QimenService.build_asking_chart(
            birth_dt, longitude, latitude, timezone_offset_hours, "终身盘"
        )
        calendar = birth_chart["calendar"]
        year_stem_index = TIANGAN.index(calendar["year_ganzhi"][0])
        forward = (gender == "男") == (year_stem_index % 2 == 0)
        reference = datetime.fromisoformat(calendar["beijing_reference_time"])
        previous_term, next_term = QimenService._month_terms_around(reference)
        target_term = next_term if forward else previous_term
        interval_days = abs((target_term["time"] - reference).total_seconds()) / 86400
        start_age = round(interval_days / 3, 2)

        month_index = JIAZI.index(calendar["month_ganzhi"])
        luck_cycles = []
        for index in range(8):
            ganzhi = JIAZI[(month_index + (index + 1) * (1 if forward else -1)) % 60]
            luck_cycles.append(
                {
                    "order": index + 1,
                    "ganzhi": ganzhi,
                    "start_age": round(start_age + index * 10, 2),
                    "end_age": round(start_age + (index + 1) * 10, 2),
                }
            )

        element_scores = {element: 0 for element in ("木", "火", "土", "金", "水")}
        for pillar in calendar["four_pillars"]:
            element_scores[STEM_ELEMENTS[pillar[0]]] += 1
            element_scores[FIVE_ELEMENTS[pillar[1]]] += 1

        selected_year = flow_year or birth_dt.year
        annual_cycles = []
        for year in range(selected_year, selected_year + 10):
            day = sxtwl.fromSolar(year, 7, 1)
            gz = day.getYearGZ()
            ganzhi = f"{TIANGAN[gz.tg]}{DIZHI[gz.dz]}"
            annual_cycles.append({"year": year, "ganzhi": ganzhi})
        monthly_cycles = []
        for month in range(1, 13):
            for day_number in range(1, 16):
                event = AstronomyService._term_on_day(datetime(selected_year, month, day_number).date())
                if event and event["index"] % 2 == 1:
                    after = event["time"] + timedelta(seconds=1)
                    month_calendar = AstronomyService.get_ganzhi_calendar(after, 120.0)
                    monthly_cycles.append(
                        {
                            "solar_term": event["name"],
                            "starts_at_beijing": event["time"].isoformat(timespec="milliseconds"),
                            "ganzhi": month_calendar["month_ganzhi"],
                        }
                    )
        return {
            "chart_type": "终身奇门",
            "birth_chart": birth_chart,
            "gender": gender,
            "luck_direction": "顺排" if forward else "逆排",
            "start_age": start_age,
            "start_age_rule": "阳男阴女顺、阴男阳女逆；出生时刻至相邻节令按三日折一年",
            "target_term": {"name": target_term["name"], "time": target_term["time"].isoformat(timespec="milliseconds")},
            "luck_cycles": luck_cycles,
            "five_element_distribution": {"unit": "四柱八字显干支计数", "scores": element_scores},
            "annual_cycles": annual_cycles,
            "monthly_cycles": monthly_cycles,
        }
