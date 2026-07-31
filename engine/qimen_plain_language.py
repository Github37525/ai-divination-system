"""把确定性奇门盘字段翻译为可读、可追溯的行动提示。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict


GATE_GUIDANCE = {
    "开门": ("可以主动推进", "尽快进入实质沟通，把目标、权限和条件说清楚", "避免只谈方向、不落实负责人和期限"),
    "生门": ("适合围绕增长和实际收益推进", "优先做能积累客户、资源或成果的事情", "避免为了短期收益忽略交付能力"),
    "休门": ("先调整节奏，再稳步推进", "先补信息、恢复状态并准备方案", "避免在准备不足时强行提速"),
    "景门": ("适合展示、表达和扩大可见度", "把成果讲清楚，用作品、数据或演示争取支持", "避免包装超过实际交付"),
    "杜门": ("当前更适合内部准备", "先排查卡点、补齐资料，等条件明确后再公开推进", "避免信息不全时仓促承诺"),
    "伤门": ("先控制摩擦和损耗", "把冲突点、成本和责任边界提前列清", "避免情绪化决策或正面硬碰"),
    "惊门": ("变化较多，宜小步验证", "准备备选方案，重要信息至少复核一次", "避免被临时消息带着仓促改变方向"),
    "死门": ("先收尾止损，不宜盲目扩张", "处理遗留问题，淘汰低效事项，再决定是否重启", "避免继续向没有反馈的方向投入"),
}

STAR_GUIDANCE = {
    "天心": "用专业判断、规则和数据来做决定",
    "天辅": "通过学习、规划和可信合作提高成功率",
    "天任": "靠持续执行和承担责任积累结果",
    "天冲": "行动速度重要，但要给快速试错留余地",
    "天英": "表达与呈现很重要，同时要用事实支撑",
    "天蓬": "机会与风险并存，先查清隐性条件",
    "天芮": "优先发现问题、修复短板，不要带病推进",
    "天柱": "沟通容易出现分歧，重要事项应书面确认",
    "天禽": "先照顾整体平衡，再处理局部得失",
}

GATE_LONG_TERM_STYLE = {
    "开门": "主动沟通、打开局面",
    "生门": "持续积累资源和成果",
    "休门": "先调整节奏，再稳步推进",
    "景门": "通过表达和展示争取机会",
    "杜门": "先准备充分，再公开行动",
    "伤门": "在竞争中提前控制损耗",
    "惊门": "用预案和小步验证应对变化",
    "死门": "先收尾重整，再重新出发",
}

CATEGORY_ACTION = {
    "综合": "把目标拆成一个本周可以验证的小结果",
    "事业": "明确当前最重要的交付、负责人和截止时间",
    "合作": "把分工、收益、期限和退出条件写清楚",
    "出行": "复核时间、路线和证件，并准备一个备选方案",
    "学业": "把学习目标拆成可检查的练习和阶段成果",
    "关系": "先表达事实与需求，再讨论立场和对错",
}


def _gate_palace(chart: Dict[str, Any]) -> Dict[str, Any]:
    position = chart["zhi_shi"]["position"]
    return next(item for item in chart["palaces"] if item["position"] == position)


def summarize_asking_chart(chart: Dict[str, Any]) -> Dict[str, Any]:
    """以值使、值符和旬空生成问事盘的白话行动摘要。"""
    gate = chart["zhi_shi"]["gate"]
    star = chart["zhi_fu"]["star"]
    category = chart.get("category", "综合")
    headline, gate_action, gate_risk = GATE_GUIDANCE[gate]
    gate_palace = _gate_palace(chart)
    actions = [CATEGORY_ACTION.get(category, CATEGORY_ACTION["综合"]), gate_action, STAR_GUIDANCE[star]]
    risks = [gate_risk]
    if gate_palace["is_void"]:
        headline = f"{headline}，但关键条件尚未完全落实"
        risks.append("值使所在宫逢旬空：先确认人、时间、资源是否真实到位")
    else:
        risks.append("值使所在宫不逢旬空：仍需用实际反馈验证盘面提示")
    return {
        "label": "问事结论",
        "headline": f"{headline}。",
        "actions": actions,
        "risks": risks,
        "basis": [
            f"值使：{gate}，落{gate_palace['name']}宫",
            f"值符：{star}",
            f"值使宫旬空：{'是' if gate_palace['is_void'] else '否'}",
        ],
        "disclaimer": "这是对确定性盘面字段的白话翻译，不代表现实结果一定发生。",
    }


def summarize_lifelong_chart(chart: Dict[str, Any]) -> Dict[str, Any]:
    """把出生盘、起运阶段与所选年份翻译为长期行动摘要。"""
    birth_chart = chart["birth_chart"]
    gate = birth_chart["zhi_shi"]["gate"]
    star = birth_chart["zhi_fu"]["star"]
    _, gate_action, gate_risk = GATE_GUIDANCE[gate]
    selected_year = chart["annual_cycles"][0]["year"]
    birth_year = datetime.fromisoformat(birth_chart["calendar"]["civil_time"]).year
    approximate_age = selected_year - birth_year
    current_cycle = next(
        (
            cycle for cycle in chart["luck_cycles"]
            if cycle["start_age"] <= approximate_age < cycle["end_age"]
        ),
        None,
    )
    if approximate_age < 0:
        stage_text = f"所选 {selected_year} 年早于出生年份，不能作为个人流年阶段"
    elif current_cycle:
        stage_text = (
            f"所选 {selected_year} 年按年份粗算约 {approximate_age} 岁，"
            f"处在第 {current_cycle['order']} 步 {current_cycle['ganzhi']} 大运"
        )
    elif approximate_age < chart["start_age"]:
        stage_text = f"所选 {selected_year} 年约 {approximate_age} 岁，尚未进入第一步大运"
    else:
        stage_text = f"所选 {selected_year} 年约 {approximate_age} 岁，超出当前展示的八步大运范围"

    scores = chart["five_element_distribution"]["scores"]
    most_visible = max(scores, key=scores.get)
    least_visible = min(scores, key=scores.get)
    return {
        "label": "长期节奏",
        "headline": f"{stage_text}；长期做事方式更适合“{GATE_LONG_TERM_STYLE[gate]}”。",
        "actions": [
            gate_action,
            STAR_GUIDANCE[star],
            f"四柱显性计数中{most_visible}较多、{least_visible}较少，可作为自我观察线索",
        ],
        "risks": [
            gate_risk,
            "年龄按年份粗算，生日之前与之后可能相差一岁",
            "五行出现次数不等同于喜用神，也不能单独判断吉凶",
        ],
        "basis": [
            f"出生盘值使：{gate}",
            f"出生盘值符：{star}",
            f"起运年龄：{chart['start_age']} 岁，方向：{chart['luck_direction']}",
            f"查看年份：{selected_year}",
        ],
        "disclaimer": "这是盘面结构与时间索引的白话说明，不是对人生事件的确定预测。",
    }
