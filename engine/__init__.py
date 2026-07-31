"""
engine/__init__.py
卜卦系统核心引擎包初始化文件
统一对外暴露排盘、历法、校验、LLM解读与审计追踪核心接口
"""

from .caster import Caster, CastingError
from .astronomy import AstronomyService
from .paipan import PaipanEngine
from .guardrails import Guardrails, GuardrailValidationError
from .llm_interpreter import LLMInterpreter
from .tracker import AuditTracker

__version__ = "2.0.0"

# 明确导出模块接口
__all__ = [
    "Caster",
    "CastingError",
    "AstronomyService",
    "PaipanEngine",
    "Guardrails",
    "GuardrailValidationError",
    "LLMInterpreter",
    "AuditTracker",
]