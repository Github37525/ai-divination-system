"""
engine/guardrails.py
熔断护栏：对排盘结果及易学逻辑极值进行硬断言
"""
class GuardrailValidationError(Exception):
    """断言失败引发的熔断异常"""
    pass

class Guardrails:
    @staticmethod
    def validate_paipan_data(paipan_data: Dict[str, Any]) -> bool:
        """校验排盘数据与逻辑断言"""
        # 1. 结构完整性检查
        required_keys = ["hexagram_code", "name", "shi_line", "moving_lines", "judgement", "lines_detail"]
        for key in required_keys:
            if key not in paipan_data or paipan_data[key] is None:
                raise GuardrailValidationError(f"排盘数据缺失关键字段: {key}")

        # 2. 6爻细节完整性检查
        lines_detail = paipan_data.get("lines_detail", {})
        if len(lines_detail) != 6:
            raise GuardrailValidationError(f"爻辞数据异常，预期6爻，实际收到 {len(lines_detail)} 爻")

        # 3. 易学逻辑极值断言
        moving_lines = paipan_data.get("moving_lines", [])
        
        # 断言：动爻索引必须在 1-6 范围内
        if any(line < 1 or line > 6 for line in moving_lines):
            raise GuardrailValidationError(f"非法动爻索引: {moving_lines}")

        # 断言：静卦时，焦点爻必须为世爻
        focus_info = paipan_data.get("focus_analysis", {})
        if len(moving_lines) == 0 and focus_info.get("primary_focus") != paipan_data.get("shi_line"):
            raise GuardrailValidationError("静卦逻辑异常：焦点爻与世爻不匹配。")

        return True