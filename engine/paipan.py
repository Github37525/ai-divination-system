"""
engine/paipan.py
负责装卦、世应纳甲匹配及焦点爻自动提炼
"""
import json
from typing import Dict, Any, List

class PaipanEngine:
    def __init__(self, db_path: str = "data/hexagrams_db.json"):
        with open(db_path, "r", encoding="utf-8") as f:
            self.db = json.load(f)

    def extract_focus_line(self, moving_lines: List[int], shi_line: int) -> Dict[str, Any]:
        """
        易学断卦核心逻辑：自动提取“焦点爻”
        规则：
        1. 静卦 (0动爻)：世爻为核心焦点。
        2. 1动爻：该动爻为核心焦点。
        3. 多动爻：选取世爻或生克主导爻为焦点，并标注主次。
        """
        num_moving = len(moving_lines)
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

    def build_paipan(self, cast_result: Dict[str, Any], calendar_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建完整排盘结构"""
        # 假设生成二进制卦码 "111111"
        hex_code = "111111" 
        hex_data = self.db.get(hex_code, {})
        
        moving_lines = cast_result.get("moving_lines", [])
        focus_info = self.extract_focus_line(moving_lines, hex_data.get("shi", 6))

        return {
            "hexagram_code": hex_code,
            "name": hex_data.get("name"),
            "palace": hex_data.get("palace"),
            "shi_line": hex_data.get("shi"),
            "ying_line": hex_data.get("ying"),
            "judgement": hex_data.get("judgement"),
            "moving_lines": moving_lines,
            "focus_analysis": focus_info,
            "calendar": calendar_data,
            "lines_detail": hex_data.get("lines", {})
        }