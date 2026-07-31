"""围绕已核验盘面的追问意图、相似问题检测与会话记忆。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, Optional


SESSION_TIMEOUT_MINUTES = 30
MAX_SESSION_TURNS = 8

FOLLOW_UP_LABELS = {
    "basis": "为什么这样判断",
    "actions": "现在可以怎么做",
    "risks": "需要留意什么",
    "focus": "只解释核心爻",
    "plain": "用更直白的话重说",
    "general": "继续解释当前结果",
}

_INTENT_PATTERNS = (
    ("basis", re.compile(r"为什么|依据|理由|怎么得出|从哪看")),
    ("actions", re.compile(r"怎么做|怎么办|行动|建议|下一步")),
    ("risks", re.compile(r"风险|注意|留意|避免|不利")),
    ("focus", re.compile(r"动爻|焦点爻|核心爻|爻辞|只解释.*爻")),
    ("plain", re.compile(r"直白|简单|通俗|看不懂|再说一次|人话")),
)
_TOPIC_PREFIXES = re.compile(r"^(请问|我想问|想问一下|帮我看看|麻烦看看|请帮我|关于)+")
_TOPIC_FILLERS = re.compile(r"是否|能不能|可不可以|怎么样|如何|一下|呢|吗|啊")
_NON_TOPIC = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


def classify_follow_up(question: str) -> str:
    """用可解释的关键词规则识别追问类型，无法识别时回到通用解释。"""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("追问内容不能为空。")
    normalized = question.strip().lower()
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(normalized):
            return intent
    return "general"


def normalize_topic(question: str) -> str:
    """删除礼貌词和弱语义填充词，保留用于相似度比较的主题字符。"""
    if not isinstance(question, str):
        return ""
    normalized = _NON_TOPIC.sub("", question.strip().lower())
    normalized = _TOPIC_PREFIXES.sub("", normalized)
    return _TOPIC_FILLERS.sub("", normalized)


def _bigrams(value: str) -> set[str]:
    if len(value) < 2:
        return {value} if value else set()
    return {value[index:index + 2] for index in range(len(value) - 1)}


def question_similarity(left: str, right: str) -> float:
    """综合字符序列与二元组相似度，返回 0-1 之间的可复核分数。"""
    first, second = normalize_topic(left), normalize_topic(right)
    if not first or not second:
        return 0.0
    if first == second:
        return 1.0
    sequence_score = SequenceMatcher(None, first, second).ratio()
    first_pairs, second_pairs = _bigrams(first), _bigrams(second)
    union = first_pairs | second_pairs
    pair_score = len(first_pairs & second_pairs) / len(union) if union else 0.0
    containment = min(len(first), len(second)) / max(len(first), len(second)) if (
        first in second or second in first
    ) else 0.0
    return round(max(sequence_score, pair_score, containment), 4)


def _utc_now(now: Optional[datetime] = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def start_session_memory(
    run_id: str,
    user_query: str,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """为当前浏览器会话建立短期上下文，不写入跨会话画像。"""
    if not run_id or not isinstance(user_query, str) or not user_query.strip():
        raise ValueError("会话记忆需要有效的运行编号和问题。")
    timestamp = _utc_now(now).isoformat(timespec="seconds")
    return {
        "active_run_id": run_id,
        "topic": user_query.strip(),
        "updated_at": timestamp,
        "turns": [],
    }


def session_memory_is_active(
    memory: Any,
    *,
    now: Optional[datetime] = None,
    timeout_minutes: int = SESSION_TIMEOUT_MINUTES,
) -> bool:
    if not isinstance(memory, dict) or not memory.get("active_run_id"):
        return False
    try:
        updated_at = datetime.fromisoformat(str(memory["updated_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    return _utc_now(now) - _utc_now(updated_at) <= timedelta(minutes=timeout_minutes)


def append_session_turn(
    memory: Dict[str, Any],
    question: str,
    answer: str,
    intent: str,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """返回更新后的会话副本，并限制携带的最近轮数。"""
    if not session_memory_is_active(memory, now=now):
        raise ValueError("当前解读会话已经过期，请先选择一条结果。")
    if intent not in FOLLOW_UP_LABELS or not question.strip() or not answer.strip():
        raise ValueError("追问记录不完整。")
    updated = dict(memory)
    turns = list(memory.get("turns", []))
    turns.append({"question": question.strip(), "answer": answer.strip(), "intent": intent})
    updated["turns"] = turns[-MAX_SESSION_TURNS:]
    updated["updated_at"] = _utc_now(now).isoformat(timespec="seconds")
    return updated


def build_offline_follow_up(ai_context: Dict[str, Any], question: str, intent: str) -> str:
    """模型不可用时，只用盘面事实和本地规则回答，不补造现实结论。"""
    summary = ai_context["paipan_summary"]
    focus = summary["焦点爻"]
    focus_text = summary["焦点爻辞"]
    label = (
        f"第 {focus['primary_focus']} 爻"
        if focus.get("primary_focus") is not None
        else focus_text.get("line_name", "特殊爻")
    )
    state_tags = []
    if focus.get("primary_focus") is not None:
        line = summary.get("六爻客观状态", {}).get(str(focus["primary_focus"]), {})
        state_tags = line.get("state_tags", [])
    state_text = "、".join(state_tags) if state_tags else "没有额外冲空破标记"

    answers = {
        "basis": (
            f"判断依据来自三层已核验信息：本卦【{summary['卦名']}】、核心焦点【{label}】以及"
            f"代码提取规则“{focus['description']}”。焦点当前{state_text}。"
        ),
        "actions": (
            "离线状态下系统不会替你推断具体决策。可以先把问题拆成一个近期可验证的小步骤，"
            f"再用【{label}】所代表的核心变量检查条件是否发生变化。"
        ),
        "risks": (
            f"当前应优先核对核心焦点【{label}】；其客观状态为“{state_text}”。"
            "不要把卦象当成医疗、法律、金融或人身安全决定的替代依据。"
        ),
        "focus": (
            f"核心是【{label} · {focus['type']}】。原典为“{focus_text['line_name']}："
            f"{focus_text['text']}”。本地规则只确认：{focus['description']}"
        ),
        "plain": (
            f"简单说，这一卦先看【{label}】，因为{focus['description']}"
            "它指出的是当前最需要核对的变量，不代表事情一定会按某个结果发生。"
        ),
        "general": (
            f"你问的是“{question.strip()}”。当前能确认的事实是本卦【{summary['卦名']}】，"
            f"核心在【{label}】；{focus['description']}更多现实映射需要 DeepSeek 可用后再生成。"
        ),
    }
    return answers[intent] + "\n\n【本地规则转译】仅解释当前已核验盘面，不构成专业建议。"


def recent_questions(turns: Iterable[Dict[str, Any]]) -> list[str]:
    return [str(turn.get("question", "")) for turn in turns if turn.get("question")][-4:]
