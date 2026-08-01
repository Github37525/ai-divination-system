"""可复用、可审计的完整六爻 Pipeline。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from engine.astronomy import AstronomyService
from engine.caster import Caster
from engine.guardrails import Guardrails
from engine.llm_interpreter import LLMInterpretationError, LLMInterpreter
from engine.paipan import PaipanEngine
from engine.quality import evaluate_interpretation
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
            "关系卦": paipan["related_hexagrams"],
            "来源分层": {
                "盘面事实": "deterministic_code",
                "原典": paipan.get("source"),
                "规则转译": "local_rule_engine",
                "模型解释": "deepseek_constrained_output",
            },
        },
    }


def _result_from_parts(
    run_id: str,
    cast_result: dict,
    calendar: dict,
    paipan: dict,
    guardrail_log: list[dict],
    ai_context: dict,
    llm_response: str,
    llm_metadata: dict,
    interpretation_status: str,
    interpretation_error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "cast_result": cast_result,
        "calendar": calendar,
        "paipan": paipan,
        "guardrail_log": guardrail_log,
        "ai_context": ai_context,
        "llm_response": llm_response,
        "llm_metadata": dict(llm_metadata),
        "interpretation_status": interpretation_status,
        "interpretation_error": interpretation_error,
    }


def run_divination_pipeline(
    user_query: str,
    casting_input: dict,
    *,
    run_id: Optional[str] = None,
    now: Optional[datetime] = None,
    interpreter: Optional[LLMInterpreter] = None,
    tracker: Optional[AuditTracker] = None,
    defer_interpretation: bool = False,
) -> Dict[str, Any]:
    """执行确定性链路并保存；模型失败时保留盘面，允许只重试解释。"""
    if not isinstance(user_query, str) or not user_query.strip():
        raise ValueError("占问事项不能为空。")
    if not isinstance(casting_input, dict):
        raise ValueError("起卦输入必须是字典。")

    if run_id is None:
        run_id = str(uuid.uuid4())
    else:
        try:
            run_id = str(uuid.UUID(run_id))
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("run_id 必须是合法 UUID。") from error
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
    interpretation_status = "pending" if defer_interpretation else "completed"
    interpretation_error = None
    try:
        llm_response = (
            llm.pending_report(ai_context)
            if defer_interpretation
            else llm.interpret(ai_context)
        )
        quality = evaluate_interpretation(llm_response, ai_context)
        if not quality["passed"]:
            raise ValueError("；".join(quality["issues"]))
    except Exception as error:
        if not isinstance(error, (ValueError, LLMInterpretationError)):
            raise
        interpretation_status = "failed"
        interpretation_error = str(error)
        llm_response = llm.failure_report(ai_context, error)
        quality = evaluate_interpretation(llm_response, ai_context)
    guardrail_log.append(
        {
            "check": "interpretation_quality",
            "status": "passed" if quality["passed"] else "failed",
            "score": quality["score"],
            "issues": quality["issues"],
        }
    )
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
    return _result_from_parts(
        run_id,
        cast_result,
        calendar,
        paipan,
        guardrail_log,
        ai_context,
        llm_response,
        llm.last_metadata,
        interpretation_status,
        interpretation_error,
    )


def retry_divination_interpretation(
    result: Dict[str, Any],
    *,
    interpreter: Optional[LLMInterpreter] = None,
    tracker: Optional[AuditTracker] = None,
    require_audit_record: bool = True,
) -> Dict[str, Any]:
    """在不重新起卦和排盘的前提下，为同一 run_id 重新生成模型解释。"""
    required = {"run_id", "ai_context", "paipan", "calendar", "guardrail_log"}
    if not isinstance(result, dict) or not required.issubset(result):
        raise ValueError("缺少可重试的确定性盘面。")
    llm = interpreter or LLMInterpreter()
    response = llm.interpret(result["ai_context"])
    quality = evaluate_interpretation(response, result["ai_context"])
    if not quality["passed"]:
        raise ValueError("重试结果未通过质量检查：" + "；".join(quality["issues"]))
    logs = [
        item for item in result["guardrail_log"]
        if item.get("check") != "interpretation_quality"
    ]
    logs.append(
        {
            "check": "interpretation_quality",
            "status": "passed",
            "score": quality["score"],
            "issues": [],
        }
    )
    audit = tracker or AuditTracker()
    updated_audit = audit.update_interpretation(
        result["run_id"], response, llm.last_metadata, logs
    )
    if require_audit_record and not updated_audit:
        raise ValueError("找不到需要重试的审计记录。")
    updated = dict(result)
    updated["llm_response"] = response
    updated["llm_metadata"] = dict(llm.last_metadata)
    updated["interpretation_status"] = "completed"
    updated["interpretation_error"] = None
    updated["guardrail_log"] = logs
    return updated


def complete_deferred_interpretation(
    result: Dict[str, Any],
    *,
    interpreter: Optional[LLMInterpreter] = None,
    tracker: Optional[AuditTracker] = None,
) -> Dict[str, Any]:
    """完成后台解释；失败时保留确定性盘面和可展示的降级报告。"""
    llm = interpreter or LLMInterpreter()
    try:
        return retry_divination_interpretation(
            result,
            interpreter=llm,
            tracker=tracker,
            require_audit_record=False,
        )
    except Exception as error:
        fallback = llm.failure_report(result["ai_context"], error)
        updated = dict(result)
        updated["llm_response"] = fallback
        updated["llm_metadata"] = dict(llm.last_metadata)
        updated["interpretation_status"] = "failed"
        updated["interpretation_error"] = str(error)
        return updated


def restore_divination_result(record: Dict[str, Any]) -> Dict[str, Any]:
    """把完整历史记录恢复为结果页可用结构。"""
    if not isinstance(record, dict) or "paipan_data" not in record:
        raise ValueError("历史记录缺少完整盘面。")
    paipan = record["paipan_data"]
    calendar = paipan.get("calendar", {})
    if "related_hexagrams" not in paipan:
        paipan = PaipanEngine().build_paipan(
            {
                "hexagram_code": paipan.get("hexagram_code"),
                "changed_hexagram_code": (
                    (paipan.get("changed_hexagram") or {}).get("hexagram_code")
                ),
                "moving_lines": paipan.get("moving_lines", []),
            },
            calendar,
        )
    ai_context = _build_ai_context(
        record["run_id"], record["user_query"], paipan, calendar
    )
    if "paipan_summary" not in ai_context:
        raise ValueError("该记录不是六爻结果，不能恢复到六爻追问区。")
    metadata = record.get("llm_metadata", {})
    return _result_from_parts(
        record["run_id"],
        {},
        calendar,
        paipan,
        record.get("guardrail_log", []),
        ai_context,
        record["llm_response"],
        metadata,
        "failed" if metadata.get("mode") == "error" else "completed",
        "历史记录中的模型解释曾失败。" if metadata.get("mode") == "error" else None,
    )


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
