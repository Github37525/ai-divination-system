"""安全随机、幂等单爻和跨设备配对会话。"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict
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
    interpretation_started_at: Optional[datetime] = None
    ai_allowed: Optional[bool] = None


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
        interpretation_runner: Optional[PipelineCallable] = None,
        session_ttl: timedelta = timedelta(minutes=30),
        pairing_ttl: timedelta = timedelta(minutes=5),
        redis_url: Optional[str] = None,
    ) -> None:
        self._pipeline = pipeline
        self._interpretation_runner = interpretation_runner
        self._session_ttl = session_ttl
        self._pairing_ttl = pairing_ttl
        self._sessions: dict[str, CastSession] = {}
        self._pairings: dict[str, PairingSession] = {}
        self._lock = threading.RLock()
        self._redis = self._connect_redis(
            os.environ.get("REDIS_URL", "").strip() if redis_url is None else redis_url
        )

    @staticmethod
    def _connect_redis(redis_url: Optional[str]) -> Any:
        if not redis_url:
            return None
        try:
            from redis import Redis

            client = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=5,
                health_check_interval=30,
            )
            client.ping()
            return client
        except Exception as error:
            if os.environ.get("EXPERIENCE_REQUIRE_REDIS", "0") == "1":
                raise RuntimeError("Redis 会话存储连接失败。") from error
            return None

    @property
    def redis_client(self) -> Any:
        return self._redis

    @property
    def backend_name(self) -> str:
        return "redis" if self._redis is not None else "memory"

    @staticmethod
    def _session_to_json(session: CastSession) -> str:
        payload = asdict(session)
        payload["seed"] = session.seed.hex()
        for key in ("created_at", "expires_at", "interpretation_started_at"):
            value = payload.get(key)
            payload[key] = value.isoformat() if isinstance(value, datetime) else None
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _session_from_json(payload: str) -> CastSession:
        data = json.loads(payload)
        data["seed"] = bytes.fromhex(data["seed"])
        for key in ("created_at", "expires_at", "interpretation_started_at"):
            data[key] = datetime.fromisoformat(data[key]) if data.get(key) else None
        return CastSession(**data)

    @staticmethod
    def _pairing_to_json(pairing: PairingSession) -> str:
        payload = asdict(pairing)
        payload["created_at"] = pairing.created_at.isoformat()
        payload["expires_at"] = pairing.expires_at.isoformat()
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _pairing_from_json(payload: str) -> PairingSession:
        data = json.loads(payload)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return PairingSession(**data)

    @staticmethod
    def _ttl_seconds(expires_at: datetime) -> int:
        return max(1, int((expires_at - _utcnow()).total_seconds()))

    def _save_session(self, session: CastSession) -> None:
        self._sessions[session.session_id] = session
        if self._redis is not None:
            self._redis.setex(
                f"experience:session:{session.session_id}",
                self._ttl_seconds(session.expires_at),
                self._session_to_json(session),
            )

    def _load_session(self, session_id: str) -> Optional[CastSession]:
        if self._redis is None:
            return self._sessions.get(session_id)
        payload = self._redis.get(f"experience:session:{session_id}")
        if not payload:
            self._sessions.pop(session_id, None)
            return None
        session = self._session_from_json(payload)
        self._sessions[session_id] = session
        return session

    def _save_pairing(self, pairing: PairingSession) -> None:
        self._pairings[pairing.pairing_id] = pairing
        if self._redis is not None:
            ttl = self._ttl_seconds(pairing.expires_at)
            pipeline = self._redis.pipeline()
            pipeline.setex(
                f"experience:pairing:{pairing.pairing_id}",
                ttl,
                self._pairing_to_json(pairing),
            )
            pipeline.setex(f"experience:pairing-code:{pairing.code}", ttl, pairing.pairing_id)
            pipeline.execute()

    def _load_pairing(self, pairing_id: str) -> Optional[PairingSession]:
        if self._redis is None:
            return self._pairings.get(pairing_id)
        payload = self._redis.get(f"experience:pairing:{pairing_id}")
        if not payload:
            self._pairings.pop(pairing_id, None)
            return None
        pairing = self._pairing_from_json(payload)
        self._pairings[pairing_id] = pairing
        return pairing

    def _load_pairing_by_code(self, code: str) -> Optional[PairingSession]:
        if self._redis is None:
            return next(
                (item for item in self._pairings.values() if item.code == code),
                None,
            )
        pairing_id = self._redis.get(f"experience:pairing-code:{code}")
        return self._load_pairing(pairing_id) if pairing_id else None

    @contextmanager
    def _distributed_lock(self, name: str):
        if self._redis is None:
            with self._lock:
                yield
            return
        lock = self._redis.lock(
            f"experience:lock:{name}", timeout=60, blocking_timeout=5
        )
        acquired = lock.acquire(blocking=True)
        if not acquired:
            raise ExperienceSessionError("会话正忙，请稍后重试。")
        try:
            with self._lock:
                yield
        finally:
            try:
                lock.release()
            except Exception:
                pass

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
        with self._distributed_lock(f"session-create:{session.session_id}"):
            self._cleanup()
            self._save_session(session)
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
        session = self._load_session(session_id)
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

        with self._distributed_lock(f"session:{session_id}"):
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
            self._save_session(session)
            return dict(response)

    def complete_cast_session(self, session_id: str, token: str) -> dict:
        with self._distributed_lock(f"session:{session_id}"):
            session = self._require_session(session_id, token)
            if session.result is not None:
                return self._completion_payload(session)
            if len(session.lines) != 6:
                raise ExperienceSessionError("必须先完成六爻才能排盘。")
            if session.status == "completing":
                raise ExperienceSessionError("排盘正在生成，请勿重复提交。")
            session.status = "completing"
            self._save_session(session)
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
            with self._distributed_lock(f"session:{session_id}"):
                current = self._load_session(session_id)
                if current is not None:
                    current.status = "ready_to_complete"
                    self._save_session(current)
            raise

        with self._distributed_lock(f"session:{session_id}"):
            session = self._require_session(session_id, token)
            session.result = result
            session.status = "completed"
            self._save_session(session)
            return self._completion_payload(session)

    def prepare_cast_session(
        self, session_id: str, token: str, *, allow_api: bool = True
    ) -> dict:
        """先完成确定性排盘，并把模型解释标记为后台待处理。"""
        with self._distributed_lock(f"session:{session_id}"):
            session = self._require_session(session_id, token)
            if session.result is not None:
                return self._completion_payload(session)
            if len(session.lines) != 6:
                raise ExperienceSessionError("必须先完成六爻才能排盘。")
            if session.status == "completing":
                raise ExperienceSessionError("排盘正在生成，请勿重复提交。")
            session.status = "completing"
            self._save_session(session)
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
            try:
                result = pipeline(
                    question,
                    casting_input,
                    run_id=run_id,
                    defer_interpretation=True,
                )
            except TypeError as error:
                if "defer_interpretation" not in str(error):
                    raise
                result = pipeline(question, casting_input, run_id=run_id)
        except Exception:
            with self._distributed_lock(f"session:{session_id}"):
                current = self._load_session(session_id)
                if current is not None:
                    current.status = "ready_to_complete"
                    self._save_session(current)
            raise

        pending = result.get("interpretation_status") == "pending"
        with self._distributed_lock(f"session:{session_id}"):
            session = self._require_session(session_id, token)
            session.result = result
            session.status = "interpretation_pending" if pending else "completed"
            session.interpretation_started_at = None
            session.ai_allowed = bool(allow_api) if pending else None
            self._save_session(session)
            return self._completion_payload(session)

    def run_pending_interpretation(
        self,
        session_id: str,
        token: str,
        *,
        allow_api: bool = True,
    ) -> dict:
        """领取并完成一个后台解释任务；崩溃后的旧领取可自动恢复。"""
        with self._distributed_lock(f"session:{session_id}"):
            session = self._require_session(session_id, token)
            if session.result is None:
                raise ExperienceSessionError("确定性盘面尚未生成。")
            if session.status in {"completed", "interpretation_failed"}:
                return self._completion_payload(session)
            now = _utcnow()
            lease_active = (
                session.status == "interpreting"
                and session.interpretation_started_at is not None
                and now - session.interpretation_started_at < timedelta(seconds=90)
            )
            if lease_active:
                return self._completion_payload(session)
            session.status = "interpreting"
            session.interpretation_started_at = now
            result = dict(session.result)
            effective_allow_api = (
                session.ai_allowed if session.ai_allowed is not None else allow_api
            )
            self._save_session(session)

        runner = self._interpretation_runner
        if runner is None:
            from engine.llm_interpreter import LLMInterpreter
            from main import complete_deferred_interpretation

            interpreter = None if effective_allow_api else LLMInterpreter(api_key="")
            updated = complete_deferred_interpretation(
                result, interpreter=interpreter
            )
        else:
            updated = runner(result, allow_api=effective_allow_api)

        with self._distributed_lock(f"session:{session_id}"):
            session = self._require_session(session_id, token)
            session.result = updated
            session.status = (
                "completed"
                if updated.get("interpretation_status") == "completed"
                else "interpretation_failed"
            )
            session.interpretation_started_at = None
            session.ai_allowed = None
            self._save_session(session)
            return self._completion_payload(session)

    def get_cast_result(self, session_id: str, token: str) -> dict:
        with self._lock:
            session = self._require_session(session_id, token)
            if session.result is None:
                raise ExperienceSessionError("确定性盘面尚未生成。")
            return self._completion_payload(session)

    @staticmethod
    def _completion_payload(session: CastSession) -> dict:
        assert session.result is not None
        paipan = session.result.get("paipan", {})
        changed = paipan.get("changed_hexagram") or {}
        llm_metadata = session.result.get("llm_metadata") or {}
        return {
            "session_id": session.session_id,
            "run_id": session.run_id,
            "status": session.status,
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
                "interpretation_mode": llm_metadata.get("mode", "unknown"),
                "ai_generated": bool(llm_metadata.get("ai_generated")),
                "model": llm_metadata.get("model"),
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
        with self._distributed_lock("pairing-create"):
            self._cleanup()
            for _ in range(20):
                code = f"{secrets.randbelow(1_000_000):06d}"
                if self._load_pairing_by_code(code) is None:
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
            self._save_pairing(pairing)
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
            pairing = self._load_pairing(pairing_id)
            if pairing is None:
                raise ExperienceSessionError("配对会话不存在或已过期。")
            if not token or not hmac.compare_digest(pairing.token, token):
                raise ExperienceSessionError("配对凭证无效。")
            return pairing

    def join_pairing_by_code(self, code: str) -> dict:
        normalized = str(code).strip()
        with self._lock:
            self._cleanup()
            pairing = self._load_pairing_by_code(normalized)
            if pairing is None:
                raise ExperienceSessionError("配对码无效或已过期。")
            cast = self._load_session(pairing.cast_session_id)
            if cast is None:
                raise ExperienceSessionError("起卦会话不存在或已过期。")
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

    def prepare_pairing(
        self, pairing_id: str, token: str, *, allow_api: bool = True
    ) -> dict:
        pairing = self.require_pairing(pairing_id, token)
        return self.prepare_cast_session(
            pairing.cast_session_id,
            pairing.cast_token,
            allow_api=allow_api,
        )

    def run_pairing_interpretation(
        self, pairing_id: str, token: str, *, allow_api: bool = True
    ) -> dict:
        pairing = self.require_pairing(pairing_id, token)
        return self.run_pending_interpretation(
            pairing.cast_session_id,
            pairing.cast_token,
            allow_api=allow_api,
        )

    def get_pairing_snapshot(self, pairing_id: str, token: str) -> dict:
        pairing = self.require_pairing(pairing_id, token)
        session = self._require_session(pairing.cast_session_id, pairing.cast_token)
        payload = self._public_session(session)
        if session.result is not None:
            payload["completion"] = self._completion_payload(session)
        return payload
