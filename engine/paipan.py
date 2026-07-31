"""
engine/paipan.py
负责装卦、世应纳甲匹配及焦点爻自动提炼
"""
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


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

    def extract_focus_line(
        self,
        moving_lines: List[int],
        shi_line: int,
        special_line: Optional[Dict[str, Any]] = None,
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
            # 多个动爻的优先分析策略
            primary = shi_line if shi_line in moving_lines else moving_lines[0]
            return {
                "primary_focus": primary,
                "secondary_focus": [m for m in moving_lines if m != primary],
                "type": "多动爻复杂局",
                "description": f"本局多爻联动，优先以第 {primary} 爻为核心矛盾点。"
            }

    @staticmethod
    def _decorate_lines(
        lines: Dict[str, Dict[str, Any]], calendar_data: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        decorated = deepcopy(lines)
        xunkong = set(calendar_data.get("xunkong", []))
        month_branch = calendar_data.get("month_branch")
        day_branch = calendar_data.get("day_branch")
        for line in decorated.values():
            branch = line.get("branch")
            line["is_xunkong"] = branch in xunkong
            line["is_month_break"] = branch == calendar_data.get("month_break_branch")
            line["is_day_clash"] = branch == calendar_data.get("day_clash_branch")
            line["is_wood_tomb"] = (
                line.get("element") == "木" and (month_branch == "未" or day_branch == "未")
            )
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
        focus_info = self.extract_focus_line(
            moving_lines, hex_data.get("shi", 6), special_line
        )
        lines_detail = self._decorate_lines(hex_data.get("lines", {}), calendar_data)
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
            "focus_analysis": focus_info,
            "focus_text": focus_text,
            "special_line": special_line,
            "calendar": calendar_data,
            "lines_detail": lines_detail,
            "source": hex_data.get("source"),
        }
