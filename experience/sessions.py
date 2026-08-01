"""安全随机、幂等单爻和跨设备配对会话。"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from engine.caster import Caster


class ExperienceSessionError(ValueError):
    """体验会话输入、权限或状态不合法。"""


PipelineCallable = Callable[..., Dict[str, Any]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class CastSession:
    session_id: str
    run_id: str
    question: str
    longitude: float
    latitude: Optional[float]
    timezone_offset_hours: float
    seed: bytes
    seed_commitment: str
    token_digest: str
    created_at: datetime
    expires_at: datetime
    lines: list[dict] = field(default_factory=list)
    idempotency_results: dict[str, dict] = field(default_factory=dict)
    status: str = "ready"
    result: Optional[dict] = None


@dataclass
class PairingSession:
    pairing_id: str
    code: str
    token: str
    cast_session_id: str
    cast_token: str
    created_at: datetime
    expires_at: datetime


class SessionStore:
    """首批实现使用进程内存；接口保持可替换为 Redis 的边界。"""

    ALGORITHM_VERSION = "hmac-sha256-three-coins-v1"

    def __init__(
        self,
        *,
        pipeline: Optional[PipelineCallable] = None,
        session_ttl: timedelta = timedelta(minutes=30),
        pairing_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        self._pipeline = pipeline
        self._session_ttl = session_ttl
        self._pairing_ttl = pairing_ttl
        self._sessions: dict[str, CastSession] = {}
        self._pairings: dict[str, PairingSession] = {}
        self._lock = threading.RLock()

    def _cleanup(self) -> None:
        now = _utcnow()
        expired_sessions = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for session_id in expired_sessions:
            del self._sessions[session_id]
        expired_pairings = [
            pairing_id
            for pairing_id, pairing in self._pairings.items()
            if pairing.expires_at <= now
        ]
        for pairing_id in expired_pairings:
            del self._pairings[pairing_id]

    @staticmethod
    def _validate_question(question: str) -> str:
        if not isinstance(question, str) or not question.strip():
            raise ExperienceSessionError("占问事项不能为空。")
        normalized = question.strip()
        if len(normalized) > 500:
            raise ExperienceSessionError("占问事项不能超过500个字符。")
        return normalized

    @staticmethod
    def _validate_coordinates(
        longitude: float,
        latitude: Optional[float],
        timezone_offset_hours: float,
    ) -> tuple[float, Optional[float], float]:
        if isinstance(longitude, bool) or not isinstance(longitude, (int, float)):
            raise ExperienceSessionError("经度必须是数字。")
        if not -180 <= float(longitude) <= 180:
            raise ExperienceSessionError("经度必须位于-180到180之间。")
        if latitude is not None:
            if isinstance(latitude, bool) or not isinstance(latitude, (int, float)):
                raise ExperienceSessionError("纬度必须是数字。")
            if not -90 <= float(latitude) <= 90:
                raise ExperienceSessionError("纬度必须位于-90到90之间。")
        if (
            isinstance(timezone_offset_hours, bool)
            or not isinstance(timezone_offset_hours, (int, float))
            or not -12 <= float(timezone_offset_hours) <= 14
        ):
            raise ExperienceSessionError("UTC时区偏移必须位于-12到14之间。")
        return (
            float(longitude),
            None if latitude is None else float(latitude),
            float(timezone_offset_hours),
        )

    def create_cast_session(
        self,
        question: str,
        *,
        longitude: float = 120.0,
        latitude: Optional[float] = None,
        timezone_offset_hours: float = 8.0,
        run_id: Optional[str] = None,
    ) -> dict:
        normalized_question = self._validate_question(question)
        longitude, latitude, timezone_offset_hours = self._validate_coordinates(
            longitude, latitude, timezone_offset_hours
        )
        now = _utcnow()
        seed = secrets.token_bytes(32)
        token = secrets.token_urlsafe(32)
        try:
            normalized_run_id = str(uuid.UUID(run_id)) if run_id else str(uuid.uuid4())
        except (ValueError, AttributeError, TypeError) as exc:
            raise ExperienceSessionError("run_id 必须是有效的 UUID。") from exc
        session = CastSession(
            session_id=str(uuid.uuid4()),
            run_id=normalized_run_id,
            question=normalized_question,
            longitude=longitude,
            latitude=latitude,
            timezone_offset_hours=timezone_offset_hours,
            seed=seed,
            seed_commitment=hashlib.sha256(seed).hexdigest(),
            token_digest=_token_digest(token),
            created_at=now,
            expires_at=now + self._session_ttl,
        )
        with self._lock:
            self._cleanup()
            self._sessions[session.session_id] = session
        return {**self._public_session(session), "session_token": token}

    @staticmethod
    def _public_session(session: CastSession) -> dict:
        return {
            "session_id": session.session_id,
            "run_id": session.run_id,
            "question": session.question,
            "status": session.status,
            "line_count": len(session.lines),
            "lines": [dict(line) for line in session.lines],
            "seed_commitment": session.seed_commitment,
            "algorithm_version": SessionStore.ALGORITHM_VERSION,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
        }

    def _require_session(self, session_id: str, token: str) -> CastSession:
        self._cleanup()
        session = self._sessions.get(session_id)
        if session is None:
            raise ExperienceSessionError("起卦会话不存在或已过期。")
        if not token or not hmac.compare_digest(
            session.token_digest, _token_digest(token)
        ):
            raise ExperienceSessionError("起卦会话凭证无效。")
        return session

    def get_cast_session(self, session_id: str, token: str) -> dict:
        with self._lock:
            return self._public_session(self._require_session(session_id, token))

    @staticmethod
    def _derive_line(seed: bytes, line_index: int) -> tuple[int, int, int]:
        digest = hmac.new(
            seed, f"line:{line_index}".encode("ascii"), hashlib.sha256
        ).digest()
        fronts = sum((digest[0] >> bit) & 1 for bit in range(3))
        reverses = 3 - fronts
        return fronts, reverses, Caster.coin_result_to_line(fronts, reverses)

    def lock_next_line(
        self,
        session_id: str,
        token: str,
        idempotency_key: str,
        *,
        motion_energy: Optional[float] = None,
        trigger_mode: str = "tap",
    ) -> dict:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ExperienceSessionError("缺少幂等键。")
        if len(idempotency_key) > 120:
            raise ExperienceSessionError("幂等键过长。")
        if trigger_mode not in {"motion", "tap", "drag", "manual", "paired"}:
            raise ExperienceSessionError("不支持的触发方式。")
        normalized_energy = None
        if motion_energy is not None:
            if isinstance(motion_energy, bool) or not isinstance(
                motion_energy, (int, float)
            ):
                raise ExperienceSessionError("动作能量必须是数字。")
            normalized_energy = round(max(0.0, min(float(motion_energy), 100.0)), 2)

        with self._lock:
            session = self._require_session(session_id, token)
            existing = session.idempotency_results.get(idempotency_key)
            if existing is not None:
                return dict(existing)
            if session.status in {"completing", "completed"}:
                raise ExperienceSessionError("本次起卦已经完成。")
            if len(session.lines) >= 6:
                raise ExperienceSessionError("六爻已经全部生成，请完成排盘。")

            line_index = len(session.lines)
            fronts, reverses, value = self._derive_line(session.seed, line_index)
            position_names = ("初爻", "二爻", "三爻", "四爻", "五爻", "上爻")
            line = {
                "line_index": line_index + 1,
                "position_name": position_names[line_index],
                "fronts": fronts,
                "reverses": reverses,
                "value": value,
                "line_type": {6: "老阴", 7: "少阳", 8: "少阴", 9: "老阳"}[value],
                "moving": value in (6, 9),
                "trigger_mode": trigger_mode,
                "motion_energy": normalized_energy,
            }
            session.lines.append(line)
            session.status = "ready_to_complete" if len(session.lines) == 6 else "ready"
            response = {
                "session_id": session.session_id,
                "run_id": session.run_id,
                "status": session.status,
                "line_count": len(session.lines),
                "line": dict(line),
            }
            session.idempotency_results[idempotency_key] = response
            return dict(response)

    def complete_cast_session(self, session_id: str, token: str) -> dict:
        with self._lock:
            session = self._require_session(session_id, token)
            if session.result is not None:
                return self._completion_payload(session)
            if len(session.lines) != 6:
                raise ExperienceSessionError("必须先完成六爻才能排盘。")
            if session.status == "completing":
                raise ExperienceSessionError("排盘正在生成，请勿重复提交。")
            session.status = "completing"
            question = session.question
            run_id = session.run_id
            casting_input = {
                "mode": "manual",
                "lines": list(reversed([line["value"] for line in session.lines])),
                "longitude": session.longitude,
                "latitude": session.latitude,
                "timezone_offset_hours": session.timezone_offset_hours,
                "experience": {
                    "algorithm_version": self.ALGORITHM_VERSION,
                    "seed_commitment": session.seed_commitment,
                    "line_triggers": [line["trigger_mode"] for line in session.lines],
                },
            }

        pipeline = self._pipeline
        if pipeline is None:
            from main import run_divination_pipeline

            pipeline = run_divination_pipeline
        try:
            result = pipeline(question, casting_input, run_id=run_id)
        except Exception:
            with self._lock:
                current = self._sessions.get(session_id)
                if current is not None:
                    current.status = "ready_to_complete"
            raise

        with self._lock:
            session = self._require_session(session_id, token)
            session.result = result
            session.status = "completed"
            return self._completion_payload(session)

    @staticmethod
    def _completion_payload(session: CastSession) -> dict:
        assert session.result is not None
        paipan = session.result.get("paipan", {})
        changed = paipan.get("changed_hexagram") or {}
        return {
            "session_id": session.session_id,
            "run_id": session.run_id,
            "status": "completed",
            "seed_commitment": session.seed_commitment,
            "seed_reveal": session.seed.hex(),
            "algorithm_version": SessionStore.ALGORITHM_VERSION,
            "lines": [dict(line) for line in session.lines],
            "result_summary": {
                "hexagram_name": paipan.get("name"),
                "changed_hexagram_name": changed.get("name"),
                "moving_lines": paipan.get("moving_lines", []),
                "focus_analysis": paipan.get("focus_analysis"),
                "interpretation_status": session.result.get("interpretation_status"),
                "interpretation": session.result.get("llm_response"),
            },
            "result": session.result,
        }

    def create_pairing_session(
        self,
        question: str,
        *,
        longitude: float = 120.0,
        latitude: Optional[float] = None,
        timezone_offset_hours: float = 8.0,
    ) -> dict:
        cast = self.create_cast_session(
            question,
            longitude=longitude,
            latitude=latitude,
            timezone_offset_hours=timezone_offset_hours,
        )
        now = _utcnow()
        with self._lock:
            self._cleanup()
            existing_codes = {pairing.code for pairing in self._pairings.values()}
            for _ in range(20):
                code = f"{secrets.randbelow(1_000_000):06d}"
                if code not in existing_codes:
                    break
            else:
                raise ExperienceSessionError("暂时无法创建配对码，请重试。")
            pairing = PairingSession(
                pairing_id=str(uuid.uuid4()),
                code=code,
                token=secrets.token_urlsafe(32),
                cast_session_id=cast["session_id"],
                cast_token=cast["session_token"],
                created_at=now,
                expires_at=now + self._pairing_ttl,
            )
            self._pairings[pairing.pairing_id] = pairing
            return self._public_pairing(pairing, cast)

    @staticmethod
    def _public_pairing(pairing: PairingSession, cast: dict) -> dict:
        return {
            "pairing_id": pairing.pairing_id,
            "pairing_code": pairing.code,
            "pairing_token": pairing.token,
            "cast_session_id": pairing.cast_session_id,
            "run_id": cast["run_id"],
            "seed_commitment": cast["seed_commitment"],
            "expires_at": pairing.expires_at.isoformat(),
        }

    def require_pairing(self, pairing_id: str, token: str) -> PairingSession:
        with self._lock:
            self._cleanup()
            pairing = self._pairings.get(pairing_id)
            if pairing is None:
                raise ExperienceSessionError("配对会话不存在或已过期。")
            if not token or not hmac.compare_digest(pairing.token, token):
                raise ExperienceSessionError("配对凭证无效。")
            return pairing

    def join_pairing_by_code(self, code: str) -> dict:
        normalized = str(code).strip()
        with self._lock:
            self._cleanup()
            pairing = next(
                (item for item in self._pairings.values() if item.code == normalized),
                None,
            )
            if pairing is None:
                raise ExperienceSessionError("配对码无效或已过期。")
            cast = self._sessions[pairing.cast_session_id]
            return self._public_pairing(pairing, self._public_session(cast))

    def lock_pairing_line(
        self,
        pairing_id: str,
        token: str,
        idempotency_key: str,
        *,
        motion_energy: Optional[float] = None,
        trigger_mode: str = "paired",
    ) -> dict:
        pairing = self.require_pairing(pairing_id, token)
        return self.lock_next_line(
            pairing.cast_session_id,
            pairing.cast_token,
            idempotency_key,
            motion_energy=motion_energy,
            trigger_mode=trigger_mode,
        )

    def complete_pairing(self, pairing_id: str, token: str) -> dict:
        pairing = self.require_pairing(pairing_id, token)
        return self.complete_cast_session(pairing.cast_session_id, pairing.cast_token)
