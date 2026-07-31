"""
engine/guardrails.py
熔断护栏：对排盘结果及易学逻辑极值进行硬断言
"""
from typing import Any, Dict


class GuardrailValidationError(Exception):
    """断言失败引发的熔断异常"""
    pass

class Guardrails:
    @staticmethod
    def validate_paipan_data(paipan_data: Dict[str, Any]) -> bool:
        """校验排盘数据与逻辑断言"""
        # 1. 结构完整性检查
        required_keys = [
            "hexagram_code",
            "name",
            "shi_line",
            "moving_lines",
            "judgement",
            "lines_detail",
            "changed_hexagram",
            "focus_analysis",
            "focus_text",
        ]
        for key in required_keys:
            if key not in paipan_data:
                raise GuardrailValidationError(f"排盘数据缺失关键字段: {key}")
        for key in required_keys:
            if key != "changed_hexagram" and paipan_data[key] is None:
                raise GuardrailValidationError(f"排盘数据关键字段为空: {key}")

        # 2. 6爻细节完整性检查
        lines_detail = paipan_data.get("lines_detail", {})
        expected_line_keys = {str(index) for index in range(1, 7)}
        required_line_fields = {
            "line_name", "text", "image", "najia", "branch", "element",
            "relative", "is_shi", "is_ying", "is_xunkong", "is_month_break",
            "is_day_clash", "is_wood_tomb",
        }
        if set(lines_detail) != expected_line_keys or any(
            not isinstance(lines_detail[key], dict)
            or not required_line_fields.issubset(lines_detail[key])
            or any(lines_detail[key][field] in (None, "") for field in required_line_fields)
            or any(
                type(lines_detail[key][field]) is not bool
                for field in (
                    "is_shi", "is_ying", "is_xunkong", "is_month_break",
                    "is_day_clash", "is_wood_tomb",
                )
            )
            for key in expected_line_keys
        ):
            raise GuardrailValidationError(f"爻辞数据异常，预期6爻，实际收到 {len(lines_detail)} 爻")
        shi_line = paipan_data.get("shi_line")
        ying_line = paipan_data.get("ying_line")
        if (
            type(shi_line) is not int
            or type(ying_line) is not int
            or not 1 <= shi_line <= 6
            or not 1 <= ying_line <= 6
            or abs(shi_line - ying_line) != 3
            or sum(bool(line["is_shi"]) for line in lines_detail.values()) != 1
            or sum(bool(line["is_ying"]) for line in lines_detail.values()) != 1
            or not lines_detail[str(shi_line)]["is_shi"]
            or not lines_detail[str(ying_line)]["is_ying"]
        ):
            raise GuardrailValidationError("世应位置与爻记录不一致。")

        # 3. 易学逻辑极值断言
        moving_lines = paipan_data.get("moving_lines", [])
        
        # 断言：动爻索引必须在 1-6 范围内
        if (
            not isinstance(moving_lines, list)
            or any(type(line) is not int or line < 1 or line > 6 for line in moving_lines)
            or len(set(moving_lines)) != len(moving_lines)
        ):
            raise GuardrailValidationError(f"非法动爻索引: {moving_lines}")

        hexagram_code = paipan_data["hexagram_code"]
        if not isinstance(hexagram_code, str) or len(hexagram_code) != 6 or set(hexagram_code) - {"0", "1"}:
            raise GuardrailValidationError(f"非法本卦卦码: {hexagram_code}")

        changed_hexagram = paipan_data["changed_hexagram"]
        if not moving_lines and changed_hexagram is not None:
            raise GuardrailValidationError("静卦逻辑异常：不应存在变卦。")
        if moving_lines:
            if not isinstance(changed_hexagram, dict):
                raise GuardrailValidationError("动卦逻辑异常：缺少变卦数据。")
            expected_bits = list(hexagram_code)
            for line in moving_lines:
                expected_bits[line - 1] = "0" if expected_bits[line - 1] == "1" else "1"
            expected_code = "".join(expected_bits)
            if changed_hexagram.get("hexagram_code") != expected_code:
                raise GuardrailValidationError(
                    f"变卦映射异常：预期 {expected_code}，实际 {changed_hexagram.get('hexagram_code')}"
                )
            if len(moving_lines) == 6 and hexagram_code in {"111111", "000000"}:
                expected_special = "用九" if hexagram_code == "111111" else "用六"
                special_line = paipan_data.get("special_line")
                if (
                    not isinstance(special_line, dict)
                    or special_line.get("line_name") != expected_special
                    or paipan_data.get("focus_text") != special_line
                ):
                    raise GuardrailValidationError(
                        f"六爻皆动的{expected_special}规则数据缺失或焦点不一致。"
                    )

        # 断言：静卦时，焦点爻必须为世爻
        focus_info = paipan_data.get("focus_analysis", {})
        if len(moving_lines) == 0 and focus_info.get("primary_focus") != paipan_data.get("shi_line"):
            raise GuardrailValidationError("静卦逻辑异常：焦点爻与世爻不匹配。")
        if len(moving_lines) == 1 and focus_info.get("primary_focus") != moving_lines[0]:
            raise GuardrailValidationError("单动爻逻辑异常：焦点爻与动爻不匹配。")
        if len(moving_lines) == 6 and hexagram_code in {"111111", "000000"}:
            if focus_info.get("primary_focus") is not None or not focus_info.get("special_line"):
                raise GuardrailValidationError("乾坤六爻皆动时必须以用九/用六为焦点。")

        return True
