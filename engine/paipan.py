"""
engine/paipan.py
负责装卦、世应纳甲匹配及焦点爻自动提炼
"""
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .config import CONTROLS, GENERATES, SIX_RELATIVES, TRIGRAM_BITS


HEXAGRAM_RELATIONS = {
    "original": ("本卦", "当前状态"),
    "changed": ("变卦", "动爻变化后的发展方向"),
    "mutual": ("互卦", "由二至五爻组成的内在过程"),
    "reversed": ("综卦", "上下倒置后的换位视角"),
    "opposite": ("错卦", "六爻阴阳全反的相反条件"),
}


class PaipanError(ValueError):
    """排盘所需规则或原典数据缺失。"""


class PaipanEngine:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        resolved_path = Path(db_path) if db_path else Path(__file__).resolve().parents[1] / "data" / "hexagrams_db.json"
        with resolved_path.open("r", encoding="utf-8") as f:
            self.db = json.load(f)

    def _get_hexagram(self, hexagram_code: str, role: str) -> Dict[str, Any]:
        hexagram = self.db.get(hexagram_code)
        if not hexagram:
            raise PaipanError(
                f"{role}卦码 {hexagram_code} 缺少权威原典数据，已按防幻觉规则中止排盘。"
            )
        return hexagram

    @staticmethod
    def derive_related_codes(
        hexagram_code: str,
        changed_hexagram_code: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """按初爻到上爻编码确定性计算本、变、互、综、错五种关系卦。"""
        for role, code in (("本", hexagram_code), ("变", changed_hexagram_code)):
            if code is not None and (
                not isinstance(code, str)
                or len(code) != 6
                or set(code) - {"0", "1"}
            ):
                raise PaipanError(f"{role}卦码不合法，无法计算关系卦。")
        return {
            "original": hexagram_code,
            "changed": changed_hexagram_code,
            "mutual": hexagram_code[1:4] + hexagram_code[2:5],
            "reversed": hexagram_code[::-1],
            "opposite": "".join("0" if bit == "1" else "1" for bit in hexagram_code),
        }

    def _build_related_hexagrams(
        self,
        hexagram_code: str,
        changed_hexagram_code: Optional[str],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        codes = self.derive_related_codes(hexagram_code, changed_hexagram_code)
        result: Dict[str, Optional[Dict[str, Any]]] = {}
        for relation, code in codes.items():
            if code is None:
                result[relation] = None
                continue
            data = self._get_hexagram(code, HEXAGRAM_RELATIONS[relation][0])
            label, meaning = HEXAGRAM_RELATIONS[relation]
            result[relation] = {
                "relation": relation,
                "label": label,
                "meaning": meaning,
                "hexagram_code": code,
                "king_wen_number": data.get("king_wen_number"),
                "symbol": data.get("symbol"),
                "name": data.get("name"),
                "upper_trigram": data.get("upper_trigram"),
                "lower_trigram": data.get("lower_trigram"),
                "judgement": data.get("judgement"),
                "source": data.get("source"),
                "is_same_as_original": code == hexagram_code,
                "provenance": "deterministic_code_and_verified_database",
            }
        return result

    def extract_focus_line(
        self,
        moving_lines: List[int],
        shi_line: int,
        special_line: Optional[Dict[str, Any]] = None,
        lines_detail: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        易学断卦核心逻辑：自动提取“焦点爻”
        规则：
        1. 静卦 (0动爻)：世爻为核心焦点。
        2. 1动爻：该动爻为核心焦点。
        3. 多动爻：选取世爻或生克主导爻为焦点，并标注主次。
        """
        num_moving = len(moving_lines)
        if num_moving == 6 and special_line:
            return {
                "primary_focus": None,
                "type": f"六爻皆动{special_line['line_name']}",
                "description": f"本局六爻皆动，按乾坤特例取{special_line['line_name']}。",
                "special_line": special_line,
            }
        if num_moving == 0:
            return {"primary_focus": shi_line, "type": "静卦世爻", "description": "本局为静卦，以世爻为核心焦点。"}
        elif num_moving == 1:
            return {"primary_focus": moving_lines[0], "type": "单动爻", "description": f"本局第 {moving_lines[0]} 爻发动，为核心变量。"}
        else:
            detail = lines_detail or {}
            shi_element = detail.get(str(shi_line), {}).get("element")

            def priority(line_number: int) -> tuple[int, int]:
                line = detail.get(str(line_number), {})
                element = line.get("element")
                score = 100 if line_number == shi_line else 0
                if element and shi_element:
                    if CONTROLS.get(element) == shi_element:
                        score += 30
                    elif GENERATES.get(element) == shi_element:
                        score += 20
                    elif GENERATES.get(shi_element) == element:
                        score += 10
                if line.get("is_ying"):
                    score += 5
                return score, -line_number

            ordered = sorted(moving_lines, key=priority, reverse=True)
            primary = ordered[0]
            return {
                "primary_focus": primary,
                "secondary_focus": ordered[1:],
                "type": "多动爻复杂局",
                "description": f"本局多爻联动，按世爻、对世爻生克及应爻顺序，以第 {primary} 爻为主焦点。",
                "priority_basis": "世爻 > 克世 > 生世 > 世生 > 应爻 > 爻位",
            }

    @staticmethod
    def _seasonal_strength(line_element: Optional[str], month_element: Optional[str]) -> str:
        if not line_element or not month_element:
            return "未知"
        if line_element == month_element:
            return "旺"
        if GENERATES[month_element] == line_element:
            return "相"
        if GENERATES[line_element] == month_element:
            return "休"
        if CONTROLS[line_element] == month_element:
            return "囚"
        return "死"

    @staticmethod
    def _flying_hidden_relation(flying_element: str, hidden_element: str) -> str:
        if flying_element == hidden_element:
            return "比和"
        if GENERATES[flying_element] == hidden_element:
            return "飞生伏"
        if CONTROLS[flying_element] == hidden_element:
            return "飞克伏"
        if GENERATES[hidden_element] == flying_element:
            return "伏生飞"
        return "伏克飞"

    def _attach_hidden_spirits(
        self,
        hex_data: Dict[str, Any],
        lines: Dict[str, Dict[str, Any]],
    ) -> None:
        present_relatives = {line.get("relative") for line in lines.values()}
        missing_relatives = SIX_RELATIVES - present_relatives
        palace_name = hex_data.get("palace_name")
        trigram_bits = TRIGRAM_BITS.get(palace_name)
        if trigram_bits is None:
            raise PaipanError(f"无法定位 {palace_name} 宫的本宫卦。")
        palace_code = "".join(str(bit) for bit in trigram_bits + trigram_bits)
        palace_hexagram = self._get_hexagram(palace_code, "本宫")
        palace_lines = palace_hexagram.get("lines", {})
        for line_number, line in lines.items():
            line["hidden_spirits"] = []
            hidden = palace_lines.get(line_number)
            if hidden and hidden.get("relative") in missing_relatives:
                line["hidden_spirits"].append(
                    {
                        "line_name": hidden["line_name"],
                        "najia": hidden["najia"],
                        "branch": hidden["branch"],
                        "element": hidden["element"],
                        "relative": hidden["relative"],
                        "source_hexagram": palace_hexagram["name"],
                        "flying_hidden_relation": self._flying_hidden_relation(
                            line["element"], hidden["element"]
                        ),
                    }
                )

    @staticmethod
    def _decorate_lines(
        lines: Dict[str, Dict[str, Any]],
        calendar_data: Dict[str, Any],
        moving_lines: Optional[List[int]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        decorated = deepcopy(lines)
        moving = set(moving_lines or [])
        xunkong = set(calendar_data.get("xunkong", []))
        month_branch = calendar_data.get("month_branch")
        day_branch = calendar_data.get("day_branch")
        month_element = calendar_data.get("month_element")
        for number, line in decorated.items():
            branch = line.get("branch")
            line_number = int(number)
            line["is_xunkong"] = branch in xunkong
            line["is_month_break"] = branch == calendar_data.get("month_break_branch")
            line["is_day_clash"] = branch == calendar_data.get("day_clash_branch")
            line["is_wood_tomb"] = (
                line.get("element") == "木" and (month_branch == "未" or day_branch == "未")
            )
            line["is_moving"] = line_number in moving
            line["seasonal_strength"] = PaipanEngine._seasonal_strength(
                line.get("element"), month_element
            )
            line["is_dark_moving"] = False
            line["is_day_break"] = False
            line["day_clash_resolution"] = None
            if line["is_day_clash"]:
                if line["is_moving"]:
                    line["day_clash_resolution"] = "明动受冲"
                elif line["is_xunkong"]:
                    line["day_clash_resolution"] = "冲空则实"
                elif line["seasonal_strength"] in {"旺", "相"}:
                    line["is_dark_moving"] = True
                    line["day_clash_resolution"] = "暗动"
                else:
                    line["is_day_break"] = True
                    line["day_clash_resolution"] = "日破"
            line["void_break_overlap"] = line["is_xunkong"] and line["is_month_break"]
            line["state_tags"] = [
                label
                for active, label in (
                    (line["is_xunkong"], "旬空"),
                    (line["is_month_break"], "月破"),
                    (line["is_dark_moving"], "暗动"),
                    (line["is_day_break"], "日破"),
                    (line["is_wood_tomb"], "木墓"),
                    (line["void_break_overlap"], "空破并见"),
                )
                if active
            ]
        return decorated

    def build_paipan(self, cast_result: Dict[str, Any], calendar_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建完整排盘结构"""
        hex_code = cast_result.get("hexagram_code")
        if not isinstance(hex_code, str) or len(hex_code) != 6 or set(hex_code) - {"0", "1"}:
            raise PaipanError("起卦结果缺少合法的六爻卦码。")

        hex_data = self._get_hexagram(hex_code, "本")
        changed_code = cast_result.get("changed_hexagram_code")
        changed_hexagram = None
        if changed_code:
            if not isinstance(changed_code, str) or len(changed_code) != 6 or set(changed_code) - {"0", "1"}:
                raise PaipanError("起卦结果包含非法的变卦卦码。")
            changed_data = self._get_hexagram(changed_code, "变")
            changed_hexagram = {
                "hexagram_code": changed_code,
                "king_wen_number": changed_data.get("king_wen_number"),
                "symbol": changed_data.get("symbol"),
                "name": changed_data.get("name"),
                "palace": changed_data.get("palace"),
                "judgement": changed_data.get("judgement"),
                "tuan": changed_data.get("tuan"),
                "image": changed_data.get("image"),
                "lines_detail": self._decorate_lines(changed_data.get("lines", {}), calendar_data),
                "special_line": changed_data.get("special_line"),
                "source": changed_data.get("source"),
            }
        
        moving_lines = cast_result.get("moving_lines", [])
        special_line = hex_data.get("special_line")
        lines_detail = self._decorate_lines(
            hex_data.get("lines", {}), calendar_data, moving_lines
        )
        self._attach_hidden_spirits(hex_data, lines_detail)
        focus_info = self.extract_focus_line(
            moving_lines, hex_data.get("shi", 6), special_line, lines_detail
        )
        primary_focus = focus_info.get("primary_focus")
        focus_text = (
            special_line
            if primary_focus is None and special_line
            else lines_detail.get(str(primary_focus))
        )

        return {
            "hexagram_code": hex_code,
            "king_wen_number": hex_data.get("king_wen_number"),
            "symbol": hex_data.get("symbol"),
            "name": hex_data.get("name"),
            "palace": hex_data.get("palace"),
            "shi_line": hex_data.get("shi"),
            "ying_line": hex_data.get("ying"),
            "judgement": hex_data.get("judgement"),
            "tuan": hex_data.get("tuan"),
            "image": hex_data.get("image"),
            "moving_lines": moving_lines,
            "changed_hexagram": changed_hexagram,
            "related_hexagrams": self._build_related_hexagrams(hex_code, changed_code),
            "focus_analysis": focus_info,
            "focus_text": focus_text,
            "special_line": special_line,
            "calendar": calendar_data,
            "lines_detail": lines_detail,
            "source": hex_data.get("source"),
        }
