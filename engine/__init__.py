"""
engine/__init__.py
统一导出核心接口
"""

from .caster import Caster, CastingError
from .astronomy import AstronomyService, AstronomyCalculationError
from .paipan import PaipanEngine, PaipanError
from .guardrails import Guardrails, GuardrailValidationError
from .llm_interpreter import LLMInterpretationError, LLMInterpreter
from .tracker import AuditTracker
from .qimen import QimenCalculationError, QimenService

__version__ = "2.1.1"

__all__ = [
    "Caster",
    "CastingError",
    "AstronomyService",
    "AstronomyCalculationError",
    "PaipanEngine",
    "PaipanError",
    "Guardrails",
    "GuardrailValidationError",
    "LLMInterpreter",
    "LLMInterpretationError",
    "AuditTracker",
    "QimenService",
    "QimenCalculationError",
]
