"""数智易学多端体验 API 与静态 H5 入口。"""
from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import qrcode

from .sessions import ExperienceSessionError, SessionStore
from .rate_limit import RateLimiter, client_identifier


WEB_ROOT = Path(__file__).resolve().parent.parent / "experience_web"


class CastSessionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    longitude: float = Field(default=120.0, ge=-180, le=180)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    timezone_offset_hours: float = Field(default=8.0, ge=-12, le=14)


class LineRequest(BaseModel):
    motion_energy: Optional[float] = Field(default=None, ge=0, le=100)
    trigger_mode: str = Field(default="tap", max_length=20)


class PairingJoinRequest(BaseModel):
    pairing_code: str = Field(min_length=6, max_length=6)


def _bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少会话凭证。")
    return authorization[7:].strip()


def _experience_error(error: ExperienceSessionError) -> HTTPException:
    message = str(error)
    status = 401 if "凭证" in message else 404 if "不存在" in message else 409
    return HTTPException(status_code=status, detail=message)


def _public_base_url(request: Request) -> str:
    configured = os.environ.get("EXPERIENCE_PUBLIC_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_hostname:
        return f"https://{render_hostname}"
    return str(request.base_url).rstrip("/")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, pairing_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(pairing_id, []).append(websocket)

    async def disconnect(self, pairing_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(pairing_id, [])
            if websocket in connections:
                connections.remove(websocket)
            if not connections:
                self._connections.pop(pairing_id, None)

    async def broadcast(self, pairing_id: str, payload: dict) -> None:
        async with self._lock:
            connections = list(self._connections.get(pairing_id, []))
        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(jsonable_encoder(payload))
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(pairing_id, websocket)


def create_app(
    store: Optional[SessionStore] = None,
    limiter: Optional[RateLimiter] = None,
) -> FastAPI:
    session_store = store or SessionStore()
    rate_limiter = limiter or RateLimiter(session_store.redis_client)
    manager = ConnectionManager()
    app = FastAPI(
        title="数智易学 Experience API",
        version="3.1.0-p0-production",
        description="手机摇卦、共享会话、分层限流、异步解释和电脑手机实时协同。",
    )
    app.state.session_store = session_store
    app.state.connection_manager = manager
    app.state.rate_limiter = rate_limiter

    def rate_limit_value(name: str, default: int) -> int:
        try:
            return max(1, int(os.environ.get(name, str(default))))
        except ValueError:
            return default

    def request_client(request: Request) -> str:
        return client_identifier(request.client.host if request.client else None)

    def enforce_limit(
        scope: str,
        identifier: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        decision = rate_limiter.hit(
            scope,
            identifier,
            limit=limit,
            window_seconds=window_seconds,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后重试。",
                headers={"Retry-After": str(decision.retry_after)},
            )

    def claim_ai_budget(identifier: str) -> bool:
        return rate_limiter.hit(
            "deepseek",
            identifier,
            limit=rate_limit_value("EXPERIENCE_AI_LIMIT_PER_HOUR", 12),
            window_seconds=3600,
        ).allowed

    ai_semaphore = asyncio.Semaphore(
        rate_limit_value("EXPERIENCE_AI_MAX_CONCURRENCY", 2)
    )

    async def finish_direct_interpretation(
        session_id: str,
        token: str,
        *,
        allow_api: bool,
    ) -> None:
        async with ai_semaphore:
            await asyncio.to_thread(
                session_store.run_pending_interpretation,
                session_id,
                token,
                allow_api=allow_api,
            )

    async def finish_pairing_interpretation(
        pairing_id: str,
        token: str,
        *,
        allow_api: bool,
    ) -> None:
        async with ai_semaphore:
            completed = await asyncio.to_thread(
                session_store.run_pairing_interpretation,
                pairing_id,
                token,
                allow_api=allow_api,
            )
        await manager.broadcast(
            pairing_id,
            {
                "type": "cast_completed",
                "session_id": completed["session_id"],
                "run_id": completed["run_id"],
                "status": completed["status"],
                "lines": completed["lines"],
                "result_summary": completed["result_summary"],
            },
        )

    allowed_origins = [
        origin.strip()
        for origin in os.environ.get("EXPERIENCE_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )

    if WEB_ROOT.exists():
        app.mount("/static", StaticFiles(directory=WEB_ROOT), name="experience-static")

    @app.get("/", include_in_schema=False)
    async def landing() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html")

    @app.get("/mobile", include_in_schema=False)
    async def mobile() -> FileResponse:
        return FileResponse(WEB_ROOT / "mobile.html")

    @app.get("/desktop", include_in_schema=False)
    async def desktop() -> FileResponse:
        return FileResponse(WEB_ROOT / "desktop.html")

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest() -> FileResponse:
        return FileResponse(
            WEB_ROOT / "manifest.webmanifest",
            media_type="application/manifest+json",
        )

    @app.get("/sw.js", include_in_schema=False)
    async def service_worker() -> FileResponse:
        return FileResponse(
            WEB_ROOT / "sw.js",
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    @app.get("/healthz")
    async def health() -> dict:
        return {
            "status": "ok",
            "service": "experience-api",
            "version": "3.1.0-p0-production",
            "session_backend": session_store.backend_name,
        }

    @app.get("/v1/config")
    async def config() -> dict:
        threshold = max(
            4.0,
            min(float(os.environ.get("EXPERIENCE_SHAKE_THRESHOLD", "11.5")), 30.0),
        )
        return {
            "motion": {
                "shake_threshold": threshold,
                "impulses_required": 3,
                "window_ms": 900,
                "cooldown_ms": 1400,
                "raw_motion_uploaded": False,
            },
            "features": {
                "motion": True,
                "haptics": True,
                "pairing": True,
                "tap_fallback": True,
                "session_resume": True,
                "async_interpretation": True,
            },
            "llm": {
                "provider": "deepseek",
                "configured": bool(os.environ.get("DEEPSEEK_API_KEY")),
                "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            },
        }

    @app.post("/v1/cast-sessions", status_code=201)
    async def create_cast_session(body: CastSessionRequest, request: Request) -> dict:
        enforce_limit(
            "cast-create",
            request_client(request),
            limit=rate_limit_value("EXPERIENCE_CREATE_LIMIT_PER_MINUTE", 10),
            window_seconds=60,
        )
        try:
            return session_store.create_cast_session(**body.model_dump())
        except ExperienceSessionError as error:
            raise _experience_error(error) from error

    @app.get("/v1/cast-sessions/{session_id}")
    async def get_cast_session(
        session_id: str, authorization: Optional[str] = Header(default=None)
    ) -> dict:
        try:
            return session_store.get_cast_session(
                session_id, _bearer_token(authorization)
            )
        except ExperienceSessionError as error:
            raise _experience_error(error) from error

    @app.post("/v1/cast-sessions/{session_id}/lines")
    async def lock_line(
        session_id: str,
        body: LineRequest,
        request: Request,
        authorization: Optional[str] = Header(default=None),
        idempotency_key: Optional[str] = Header(
            default=None, alias="Idempotency-Key"
        ),
    ) -> dict:
        enforce_limit(
            "line-lock",
            f"{request_client(request)}:{session_id}",
            limit=rate_limit_value("EXPERIENCE_LINE_LIMIT_PER_MINUTE", 30),
            window_seconds=60,
        )
        try:
            return session_store.lock_next_line(
                session_id,
                _bearer_token(authorization),
                idempotency_key or "",
                motion_energy=body.motion_energy,
                trigger_mode=body.trigger_mode,
            )
        except ExperienceSessionError as error:
            raise _experience_error(error) from error

    @app.post("/v1/cast-sessions/{session_id}/complete")
    async def complete_cast(
        session_id: str,
        request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> Response:
        token = _bearer_token(authorization)
        identifier = request_client(request)
        enforce_limit(
            "cast-complete",
            f"{identifier}:{session_id}",
            limit=rate_limit_value("EXPERIENCE_COMPLETE_LIMIT_PER_MINUTE", 4),
            window_seconds=60,
        )
        allow_api = claim_ai_budget(identifier)
        try:
            prepared = await asyncio.to_thread(
                session_store.prepare_cast_session,
                session_id,
                token,
                allow_api=allow_api,
            )
        except ExperienceSessionError as error:
            raise _experience_error(error) from error

        if prepared["status"] == "interpretation_pending":
            asyncio.create_task(
                finish_direct_interpretation(
                    session_id,
                    token,
                    allow_api=allow_api,
                )
            )
            return JSONResponse(status_code=202, content=jsonable_encoder(prepared))
        return JSONResponse(status_code=200, content=jsonable_encoder(prepared))

    @app.get("/v1/cast-sessions/{session_id}/result")
    async def get_cast_result(
        session_id: str,
        request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> Response:
        token = _bearer_token(authorization)
        try:
            result = session_store.get_cast_result(session_id, token)
        except ExperienceSessionError as error:
            raise _experience_error(error) from error
        if result["status"] == "interpretation_pending":
            asyncio.create_task(
                finish_direct_interpretation(
                    session_id,
                    token,
                    allow_api=False,
                )
            )
        status_code = 202 if result["status"] in {"interpretation_pending", "interpreting"} else 200
        return JSONResponse(status_code=status_code, content=jsonable_encoder(result))

    @app.post("/v1/pairing-sessions", status_code=201)
    async def create_pairing(body: CastSessionRequest, request: Request) -> dict:
        enforce_limit(
            "pairing-create",
            request_client(request),
            limit=rate_limit_value("EXPERIENCE_PAIRING_LIMIT_PER_MINUTE", 6),
            window_seconds=60,
        )
        try:
            pairing = session_store.create_pairing_session(**body.model_dump())
        except ExperienceSessionError as error:
            raise _experience_error(error) from error
        public_base = _public_base_url(request)
        pairing["mobile_url"] = (
            f"{public_base}/mobile?pairing={pairing['pairing_id']}"
            f"&token={pairing['pairing_token']}"
        )
        pairing["qr_url"] = (
            f"/v1/pairing-sessions/{pairing['pairing_id']}/qr.png"
            f"?token={pairing['pairing_token']}"
        )
        pairing["desktop_url"] = f"{public_base}/desktop"
        return pairing

    @app.get("/v1/pairing-sessions/{pairing_id}/qr.png", include_in_schema=False)
    async def pairing_qr(
        pairing_id: str,
        request: Request,
        token: str = Query(...),
    ) -> Response:
        try:
            pairing = session_store.require_pairing(pairing_id, token)
        except ExperienceSessionError as error:
            raise _experience_error(error) from error
        public_base = _public_base_url(request)
        mobile_url = (
            f"{public_base}/mobile?pairing={pairing.pairing_id}"
            f"&token={pairing.token}"
        )
        image = qrcode.make(mobile_url)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return Response(
            output.getvalue(),
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/v1/pairing-sessions/join")
    async def join_pairing(body: PairingJoinRequest, request: Request) -> dict:
        try:
            pairing = session_store.join_pairing_by_code(body.pairing_code)
        except ExperienceSessionError as error:
            raise _experience_error(error) from error
        public_base = _public_base_url(request)
        pairing["mobile_url"] = (
            f"{public_base}/mobile?pairing={pairing['pairing_id']}"
            f"&token={pairing['pairing_token']}"
        )
        return pairing

    @app.websocket("/v1/pairing-sessions/{pairing_id}/ws")
    async def pairing_websocket(
        websocket: WebSocket,
        pairing_id: str,
        token: str = Query(...),
        role: str = Query(default="mobile", pattern="^(mobile|desktop)$"),
    ) -> None:
        try:
            pairing = session_store.require_pairing(pairing_id, token)
        except ExperienceSessionError:
            await websocket.close(code=4401, reason="配对凭证无效。")
            return

        await manager.connect(pairing_id, websocket)
        client_id = client_identifier(
            websocket.client.host if websocket.client else None,
        )
        snapshot = session_store.get_pairing_snapshot(pairing_id, token)
        await websocket.send_json(
            jsonable_encoder({"type": "session_snapshot", **snapshot})
        )
        snapshot_completion = snapshot.get("completion") or {}
        if snapshot_completion.get("status") in {"interpretation_pending", "interpreting"}:
            asyncio.create_task(
                finish_pairing_interpretation(
                    pairing_id,
                    token,
                    allow_api=False,
                )
            )
        await manager.broadcast(
            pairing_id,
            {
                "type": "peer_status",
                "role": role,
                "status": "connected",
                "pairing_id": pairing_id,
            },
        )
        try:
            while True:
                message: dict[str, Any] = await websocket.receive_json()
                message_type = message.get("type")
                if message_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
                if message_type == "lock_line":
                    if role != "mobile":
                        await websocket.send_json(
                            {"type": "error", "message": "只有手机端可以触发摇卦。"}
                        )
                        continue
                    decision = rate_limiter.hit(
                        "pairing-line",
                        f"{client_id}:{pairing_id}",
                        limit=rate_limit_value("EXPERIENCE_LINE_LIMIT_PER_MINUTE", 30),
                        window_seconds=60,
                    )
                    if not decision.allowed:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "摇卦操作过于频繁，请稍后再试。",
                                "retry_after": decision.retry_after,
                            }
                        )
                        continue
                    try:
                        line = session_store.lock_pairing_line(
                            pairing_id,
                            token,
                            str(message.get("idempotency_key", "")),
                            motion_energy=message.get("motion_energy"),
                            trigger_mode=(
                                "motion" if message.get("trigger_mode") == "motion" else "paired"
                            ),
                        )
                    except ExperienceSessionError as error:
                        await websocket.send_json(
                            {"type": "error", "message": str(error)}
                        )
                        continue
                    await manager.broadcast(pairing_id, {"type": "line_locked", **line})
                    continue
                if message_type == "complete":
                    allow_api = claim_ai_budget(client_id)
                    try:
                        prepared = await asyncio.to_thread(
                            session_store.prepare_pairing,
                            pairing_id,
                            token,
                            allow_api=allow_api,
                        )
                    except ExperienceSessionError as error:
                        await websocket.send_json(
                            {"type": "error", "message": str(error)}
                        )
                        continue
                    await manager.broadcast(
                        pairing_id,
                        {
                            "type": "cast_prepared",
                            "session_id": prepared["session_id"],
                            "run_id": prepared["run_id"],
                            "status": prepared["status"],
                            "lines": prepared["lines"],
                            "result_summary": prepared["result_summary"],
                        },
                    )
                    if prepared["status"] == "interpretation_pending":
                        asyncio.create_task(
                            finish_pairing_interpretation(
                                pairing_id,
                                token,
                                allow_api=allow_api,
                            )
                        )
                    continue
                await websocket.send_json(
                    {"type": "error", "message": "不支持的实时消息类型。"}
                )
        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect(pairing_id, websocket)
            await manager.broadcast(
                pairing_id,
                {"type": "peer_status", "role": role, "status": "disconnected"},
            )

    return app


app = create_app()
