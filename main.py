"""可复用、可审计的完整六爻 Pipeline。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from engine.astronomy import AstronomyService
from engine.caster import Caster
from engine.guardrails import Guardrails
from engine.llm_interpreter import LLMInterpreter
from engine.paipan import PaipanEngine
from engine.tracker import AuditTracker


def _build_ai_context(run_id: str, user_query: str, paipan: dict, calendar: dict) -> dict:
    return {
        "run_id": run_id,
        "user_query": user_query,
        "paipan_summary": {
            "卦名": paipan["name"],
            "宫位": paipan["palace"],
            "干支": calendar["day_ganzhi"],
            "四柱": calendar["four_pillars"],
            "世爻": paipan["shi_line"],
            "应爻": paipan["ying_line"],
            "旬空": calendar["xunkong"],
            "六神": calendar["liushen"],
            "焦点爻": paipan["focus_analysis"],
            "卦辞原典": paipan["judgement"],
            "焦点爻辞": paipan["focus_text"],
            "六爻客观状态": paipan["lines_detail"],
        },
    }


def run_divination_pipeline(
    user_query: str,
    casting_input: dict,
    *,
    now: Optional[datetime] = None,
    interpreter: Optional[LLMInterpreter] = None,
    tracker: Optional[AuditTracker] = None,
) -> Dict[str, Any]:
    """执行起卦、历法、排盘、护栏、解读与审计，失败时直接抛出原始异常。"""
    if not isinstance(user_query, str) or not user_query.strip():
        raise ValueError("占问事项不能为空。")
    if not isinstance(casting_input, dict):
        raise ValueError("起卦输入必须是字典。")

    run_id = str(uuid.uuid4())
    cast_mode = casting_input.get("mode", "manual")
    if cast_mode == "manual":
        cast_result = Caster.cast_manual(casting_input.get("lines"))
    elif cast_mode == "number":
        cast_result = Caster.cast_number(casting_input.get("numbers"))
    else:
        raise ValueError(f"不支持的起卦模式: {cast_mode}")

    offset = casting_input.get("timezone_offset_hours", 8.0)
    calculation_time = now or datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=offset))
    )
    calendar = AstronomyService.get_ganzhi_calendar(
        calculation_time,
        casting_input.get("longitude", 120.0),
        casting_input.get("latitude"),
        offset,
    )
    paipan = PaipanEngine().build_paipan(cast_result, calendar)
    Guardrails.validate_paipan_data(paipan)
    guardrail_log = [
        {"check": "structure", "status": "passed"},
        {"check": "hexagram_transition", "status": "passed"},
        {"check": "rule_conflicts", "status": "passed"},
    ]
    ai_context = _build_ai_context(run_id, user_query.strip(), paipan, calendar)
    llm = interpreter or LLMInterpreter()
    llm_response = llm.interpret(ai_context)
    audit = tracker or AuditTracker()
    audit.save_run_record(
        run_id,
        user_query,
        casting_input,
        paipan,
        ai_context,
        llm_response,
        guardrail_log,
        llm.last_metadata,
    )
    return {
        "run_id": run_id,
        "cast_result": cast_result,
        "calendar": calendar,
        "paipan": paipan,
        "guardrail_log": guardrail_log,
        "ai_context": ai_context,
        "llm_response": llm_response,
        "llm_metadata": dict(llm.last_metadata),
    }


if __name__ == "__main__":
    result = run_divination_pipeline(
        "今年适合跳槽吗？",
        {
            "mode": "manual",
            "lines": [8, 8, 8, 8, 8, 8],
            "longitude": 120.15,
            "latitude": 30.28,
            "timezone_offset_hours": 8.0,
        },
    )
    print(f"Pipeline 完成，Run ID: {result['run_id']}")
