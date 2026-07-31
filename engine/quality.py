"""对最终解读做可重复的事实、结构与合规质量检查。"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .llm_interpreter import DISCLAIMER, HIGH_RISK_NOTICE, HIGH_RISK_PATTERN


REQUIRED_SECTIONS = (
    "#### 一、盘面事实陈述",
    "#### 二、典籍语义解析",
    "#### 三、现实问题映射与建议",
)
FORBIDDEN_CERTAINTY = re.compile(
    r"百分之百|100%|一定会|必然会|绝对会|保证(?:成功|盈利|胜诉|治愈)"
)


def evaluate_interpretation(report: str, ai_context: Dict[str, Any]) -> Dict[str, Any]:
    """返回机器可读的质量结果；不评价易学结论，只检查可验证约束。"""
    issues: List[str] = []
    if not isinstance(report, str) or not report.strip():
        return {"passed": False, "score": 0.0, "issues": ["解读为空"]}

    for section in REQUIRED_SECTIONS:
        if section not in report:
            issues.append(f"缺少结构：{section.replace('#', '').strip()}")

    summary = ai_context.get("paipan_summary", {})
    verified_values = {
        "卦名": summary.get("卦名"),
        "卦辞": summary.get("卦辞原典"),
        "焦点爻辞": (summary.get("焦点爻辞") or {}).get("text"),
    }
    for label, value in verified_values.items():
        if value and str(value) not in report:
            issues.append(f"未回填已核验{label}")

    if DISCLAIMER not in report:
        issues.append("缺少统一免责声明")
    if FORBIDDEN_CERTAINTY.search(report):
        issues.append("包含禁止的确定性承诺")
    query = str(ai_context.get("user_query", ""))
    if HIGH_RISK_PATTERN.search(query) and HIGH_RISK_NOTICE not in report:
        issues.append("高风险问题缺少专业咨询提示")

    checks = len(REQUIRED_SECTIONS) + len(verified_values) + 3
    score = round(max(0.0, (checks - len(issues)) / checks), 3)
    return {"passed": not issues, "score": score, "issues": issues}
