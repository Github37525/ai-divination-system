"""
engine/caster.py
负责起卦输入校验与转化，确保输入的合法性
"""
from typing import List, Dict, Any

class CastingError(ValueError):
    """起卦输入非法抛出的异常"""
    pass

class Caster:
    @staticmethod
    def cast_number(numbers: List[int]) -> Dict[str, Any]:
        """
        数字起卦校验与推算
        :param numbers: 3个整数组成的列表，如 [123, 456, 789]
        """
        if len(numbers) != 3 or not all(isinstance(x, int) and 0 <= x <= 999 for x in numbers):
            raise CastingError("数字起卦必须包含3个位于0-999之间的整数。")

        upper_code = numbers[0] % 8
        upper_code = 8 if upper_code == 0 else upper_code

        lower_code = numbers[1] % 8
        lower_code = 8 if lower_code == 0 else lower_code

        moving_line = numbers[2] % 6
        moving_line = 6 if moving_line == 0 else moving_line

        return {
            "method": "number",
            "upper_trigram_id": upper_code,
            "lower_trigram_id": lower_code,
            "moving_lines": [moving_line]
        }

    @staticmethod
    def cast_manual(lines: List[int]) -> Dict[str, Any]:
        """
        手摇卦/手动录入校验与映射
        :param lines: 6个爻的状态列表（页面录入从上到下：上爻到初爻，值为：6老阴, 7少阳, 8少阴, 9老阳）
        """
        if len(lines) != 6 or not all(x in [6, 7, 8, 9] for x in lines):
            raise CastingError("手摇卦必须包含6个合法爻值 (6, 7, 8, 9)。")

        # 核心映射逻辑：页面输入为从上到下，转换成标准从初爻到上爻（Bottom-to-Top）
        standard_lines = list(reversed(lines))
        moving_lines = [i + 1 for i, val in enumerate(standard_lines) if val in [6, 9]]

        return {
            "method": "manual",
            "raw_input_lines": lines,
            "standard_lines": standard_lines,  # 顺序：[初爻, 二爻, 三爻, 四爻, 五爻, 上爻]
            "moving_lines": moving_lines
        }