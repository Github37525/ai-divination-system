"""
engine/caster.py
负责起卦输入校验与转化，确保输入的合法性
"""
from typing import Any, Dict, List, Optional, Tuple

from .config import BAGUA_XIANTIAN, TRIGRAM_BITS

class CastingError(ValueError):
    """起卦输入非法抛出的异常"""
    pass

class Caster:
    @staticmethod
    def coin_result_to_line(fronts: int, reverses: int) -> int:
        """把三枚铜钱的正反面结果换算为 6-9 爻值（正=3，反=2）。"""
        if (
            type(fronts) is not int
            or type(reverses) is not int
            or fronts < 0
            or reverses < 0
            or fronts + reverses != 3
        ):
            raise CastingError("铜钱结果必须由3枚硬币组成，且正反面数量不能为负数。")
        return fronts * 3 + reverses * 2

    @staticmethod
    def _build_hexagram_codes(standard_lines: List[int]) -> Tuple[str, Optional[str]]:
        """根据初爻到上爻的爻值生成本卦与变卦二进制码。"""
        original_bits = [1 if line in (7, 9) else 0 for line in standard_lines]
        moving_indexes = [index for index, line in enumerate(standard_lines) if line in (6, 9)]
        changed_bits = original_bits.copy()
        for index in moving_indexes:
            changed_bits[index] = 1 - changed_bits[index]

        original_code = "".join(str(bit) for bit in original_bits)
        changed_code = "".join(str(bit) for bit in changed_bits) if moving_indexes else None
        return original_code, changed_code

    @staticmethod
    def cast_number(numbers: List[int]) -> Dict[str, Any]:
        """
        数字起卦校验与推算
        :param numbers: 3个整数组成的列表，如 [123, 456, 789]
        """
        if (
            not isinstance(numbers, (list, tuple))
            or len(numbers) != 3
            or not all(type(value) is int and 0 <= value <= 999 for value in numbers)
        ):
            raise CastingError("数字起卦必须包含3个位于0-999之间的整数。")

        upper_code = numbers[0] % 8
        upper_code = 8 if upper_code == 0 else upper_code

        lower_code = numbers[1] % 8
        lower_code = 8 if lower_code == 0 else lower_code

        moving_line = numbers[2] % 6
        moving_line = 6 if moving_line == 0 else moving_line

        lower_name = BAGUA_XIANTIAN[lower_code]
        upper_name = BAGUA_XIANTIAN[upper_code]
        original_bits = list(TRIGRAM_BITS[lower_name] + TRIGRAM_BITS[upper_name])
        changed_bits = original_bits.copy()
        changed_bits[moving_line - 1] = 1 - changed_bits[moving_line - 1]

        return {
            "method": "number",
            "upper_trigram_id": upper_code,
            "lower_trigram_id": lower_code,
            "moving_lines": [moving_line],
            "hexagram_code": "".join(str(bit) for bit in original_bits),
            "changed_hexagram_code": "".join(str(bit) for bit in changed_bits),
        }

    @staticmethod
    def cast_manual(lines: List[int]) -> Dict[str, Any]:
        """
        手摇卦/手动录入校验与映射
        :param lines: 6个爻的状态列表（页面录入从上到下：上爻到初爻，值为：6老阴, 7少阳, 8少阴, 9老阳）
        """
        if (
            not isinstance(lines, (list, tuple))
            or len(lines) != 6
            or not all(type(value) is int and value in (6, 7, 8, 9) for value in lines)
        ):
            raise CastingError("手摇卦必须包含6个合法爻值 (6, 7, 8, 9)。")

        # 核心映射逻辑：页面输入为从上到下，转换成标准从初爻到上爻（Bottom-to-Top）
        standard_lines = list(reversed(lines))
        moving_lines = [i + 1 for i, val in enumerate(standard_lines) if val in [6, 9]]
        hexagram_code, changed_hexagram_code = Caster._build_hexagram_codes(standard_lines)

        return {
            "method": "manual",
            "raw_input_lines": list(lines),
            "standard_lines": standard_lines,  # 顺序：[初爻, 二爻, 三爻, 四爻, 五爻, 上爻]
            "moving_lines": moving_lines,
            "hexagram_code": hexagram_code,
            "changed_hexagram_code": changed_hexagram_code,
        }
