"""四柱、节气、真太阳时、旬空与六神的纯 Python 历法引擎。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from math import cos, isfinite, pi, sin
from typing import Any, Dict, Optional

from lunar_python import Solar

from .config import DIZHI, FIVE_ELEMENTS, LIUSHEN_MAP, TIANGAN


JIEQI_NAMES = (
    "冬至", "小寒", "大寒", "立春", "雨水", "惊蛰",
    "春分", "清明", "谷雨", "立夏", "小满", "芒种",
    "夏至", "小暑", "大暑", "立秋", "处暑", "白露",
    "秋分", "寒露", "霜降", "立冬", "小雪", "大雪",
)
BEIJING_OFFSET_HOURS = 8.0


class AstronomyCalculationError(ValueError):
    """天文历法输入不合法或无法计算。"""


def _validate_number(value: float, label: str, minimum: float, maximum: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not minimum <= float(value) <= maximum
    ):
        raise AstronomyCalculationError(
            f"{label}必须是 {minimum:g} 到 {maximum:g} 之间的有限数值。"
        )
    return float(value)


def _solar_to_datetime(value: Solar) -> datetime:
    return datetime(
        value.getYear(), value.getMonth(), value.getDay(),
        value.getHour(), value.getMinute(), value.getSecond(),
    )


def _format_time(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds")


@lru_cache(maxsize=64)
def _jieqi_events_for_year(year: int) -> tuple[tuple[int, str, datetime], ...]:
    """返回该公历年节气表；冬至项指向上一年冬至，便于跨年定位。"""
    table = Solar.fromYmdHms(year, 7, 1, 12, 0, 0).getLunar().getJieQiTable()
    events = []
    for index, name in enumerate(JIEQI_NAMES):
        value = table.get(name)
        if value is not None:
            events.append((index, name, _solar_to_datetime(value)))
    return tuple(events)


class AstronomyService:
    """按北京时间节气边界和本地真太阳钟计算六爻与奇门历法字段。"""

    @staticmethod
    def equation_of_time_minutes(dt: datetime) -> float:
        """NOAA fractional-year 公式计算均时差（视太阳时－平太阳时）。"""
        if not isinstance(dt, datetime):
            raise AstronomyCalculationError("时间必须是 datetime 实例。")
        day_number = dt.timetuple().tm_yday
        hour = dt.hour + dt.minute / 60 + dt.second / 3600 + dt.microsecond / 3_600_000_000
        days_in_year = 366 if date(dt.year, 12, 31).timetuple().tm_yday == 366 else 365
        gamma = 2 * pi / days_in_year * (day_number - 1 + (hour - 12) / 24)
        return 229.18 * (
            0.000075
            + 0.001868 * cos(gamma)
            - 0.032077 * sin(gamma)
            - 0.014615 * cos(2 * gamma)
            - 0.040849 * sin(2 * gamma)
        )

    @staticmethod
    def calculate_true_solar_time(
        dt: datetime,
        longitude: float,
        timezone_offset_hours: float = BEIJING_OFFSET_HOURS,
    ) -> datetime:
        """把当地民用时换算为当地视太阳时。"""
        if not isinstance(dt, datetime):
            raise AstronomyCalculationError("时间必须是 datetime 实例。")
        longitude = _validate_number(longitude, "经度", -180, 180)
        offset_hours = AstronomyService._resolve_timezone_offset(dt, timezone_offset_hours)
        standard_meridian = 15.0 * offset_hours
        longitude_correction = 4.0 * (longitude - standard_meridian)
        correction = longitude_correction + AstronomyService.equation_of_time_minutes(dt)
        return dt + timedelta(minutes=correction)

    @staticmethod
    def _resolve_timezone_offset(dt: datetime, supplied_offset: float) -> float:
        supplied_offset = _validate_number(supplied_offset, "UTC 时区偏移", -12, 14)
        if dt.tzinfo is None:
            return supplied_offset
        actual = dt.utcoffset()
        if actual is None:
            raise AstronomyCalculationError("无法读取时间对象的 UTC 时区偏移。")
        return actual.total_seconds() / 3600

    @staticmethod
    def _beijing_reference_time(dt: datetime, offset_hours: float) -> datetime:
        aware = dt if dt.tzinfo is not None else dt.replace(
            tzinfo=timezone(timedelta(hours=offset_hours))
        )
        return aware.astimezone(
            timezone(timedelta(hours=BEIJING_OFFSET_HOURS))
        ).replace(tzinfo=None)

    @staticmethod
    def _term_on_day(day_value: date) -> Optional[dict[str, Any]]:
        for year in (day_value.year, day_value.year + 1):
            for index, name, moment in _jieqi_events_for_year(year):
                if moment.date() == day_value:
                    return {"index": index, "name": name, "time": moment}
        return None

    @staticmethod
    def _surrounding_terms(reference_time: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
        unique = {}
        for year in (reference_time.year, reference_time.year + 1):
            for index, name, moment in _jieqi_events_for_year(year):
                unique[(name, moment)] = {"index": index, "name": name, "time": moment}
        events = sorted(unique.values(), key=lambda item: item["time"])
        previous = next((item for item in reversed(events) if item["time"] <= reference_time), None)
        following = next((item for item in events if item["time"] > reference_time), None)
        if previous is None or following is None:
            raise AstronomyCalculationError("无法定位当前时刻前后的节气。")
        return previous, following

    @staticmethod
    def _year_month_ganzhi(reference_time: datetime) -> tuple[str, str]:
        lunar = Solar.fromYmdHms(
            reference_time.year, reference_time.month, reference_time.day,
            reference_time.hour, reference_time.minute, reference_time.second,
        ).getLunar()
        eight_char = lunar.getEightChar()
        return eight_char.getYear(), eight_char.getMonth()

    @staticmethod
    def get_ganzhi_calendar(
        dt: datetime,
        longitude: float = 120.0,
        latitude: Optional[float] = None,
        timezone_offset_hours: float = BEIJING_OFFSET_HOURS,
    ) -> Dict[str, Any]:
        """计算四柱及六爻历法字段；默认采用晚子时（23:00）换日。"""
        if not isinstance(dt, datetime):
            raise AstronomyCalculationError("时间必须是 datetime 实例。")
        longitude = _validate_number(longitude, "经度", -180, 180)
        if latitude is not None:
            latitude = _validate_number(latitude, "纬度", -90, 90)
        offset_hours = AstronomyService._resolve_timezone_offset(dt, timezone_offset_hours)

        try:
            true_dt = AstronomyService.calculate_true_solar_time(dt, longitude, offset_hours)
            reference_time = AstronomyService._beijing_reference_time(dt, offset_hours)
            year_text, month_text = AstronomyService._year_month_ganzhi(reference_time)

            day_date = true_dt.date()
            if true_dt.hour == 23:
                day_date += timedelta(days=1)
            day_eight_char = Solar.fromYmdHms(
                day_date.year, day_date.month, day_date.day, 12, 0, 0
            ).getLunar().getEightChar()
            day_text = day_eight_char.getDay()
            day_stem_index = TIANGAN.index(day_text[0])
            day_branch_index = DIZHI.index(day_text[1])
            hour_branch_index = ((true_dt.hour + 1) // 2) % 12
            hour_stem_index = ((day_stem_index % 5) * 2 + hour_branch_index) % 10
            hour_text = f"{TIANGAN[hour_stem_index]}{DIZHI[hour_branch_index]}"
            previous_term, next_term = AstronomyService._surrounding_terms(reference_time)
        except AstronomyCalculationError:
            raise
        except Exception as error:
            raise AstronomyCalculationError(f"历法计算失败：{error}") from error

        month_branch_index = DIZHI.index(month_text[1])
        xunkong_start = (day_branch_index - day_stem_index - 2) % 12
        standard_meridian = 15.0 * offset_hours
        longitude_correction = 4.0 * (longitude - standard_meridian)
        equation_of_time = AstronomyService.equation_of_time_minutes(dt)
        return {
            "civil_time": _format_time(dt),
            "beijing_reference_time": _format_time(reference_time),
            "true_solar_time": _format_time(true_dt),
            "longitude": longitude,
            "latitude": latitude,
            "timezone_offset_hours": offset_hours,
            "standard_meridian": standard_meridian,
            "longitude_correction_minutes": round(longitude_correction, 6),
            "equation_of_time_minutes": round(equation_of_time, 6),
            "year_ganzhi": year_text,
            "month_ganzhi": month_text,
            "day_ganzhi": day_text,
            "hour_ganzhi": hour_text,
            "four_pillars": [year_text, month_text, day_text, hour_text],
            "month_branch": DIZHI[month_branch_index],
            "month_element": FIVE_ELEMENTS[DIZHI[month_branch_index]],
            "day_branch": DIZHI[day_branch_index],
            "day_element": FIVE_ELEMENTS[DIZHI[day_branch_index]],
            "xunkong": [DIZHI[xunkong_start], DIZHI[(xunkong_start + 1) % 12]],
            "liushen": LIUSHEN_MAP[TIANGAN[day_stem_index]],
            "month_break_branch": DIZHI[(month_branch_index + 6) % 12],
            "day_clash_branch": DIZHI[(day_branch_index + 6) % 12],
            "wood_tomb_branch": "未",
            "day_rollover_rule": "晚子时23:00换日",
            "current_solar_term": {
                "name": previous_term["name"],
                "time": _format_time(previous_term["time"]),
            },
            "next_solar_term": {
                "name": next_term["name"],
                "time": _format_time(next_term["time"]),
            },
            "calendar_backend": "lunar-python 1.4.8 (MIT, pure Python)",
        }
