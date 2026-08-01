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
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import qrcode

from .sessions import ExperienceSessionError, SessionStore


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


def create_app(store: Optional[SessionStore] = None) -> FastAPI:
    session_store = store or SessionStore()
    manager = ConnectionManager()
    app = FastAPI(
        title="数智易学 Experience API",
        version="3.0.0-p0",
        description="手机摇卦、幂等六爻和电脑手机实时协同。",
    )
    app.state.session_store = session_store
    app.state.connection_manager = manager

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
        return {"status": "ok", "service": "experience-api", "version": "3.0.0-p0"}

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
            },
        }

    @app.post("/v1/cast-sessions", status_code=201)
    async def create_cast_session(body: CastSessionRequest) -> dict:
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
        authorization: Optional[str] = Header(default=None),
        idempotency_key: Optional[str] = Header(
            default=None, alias="Idempotency-Key"
        ),
    ) -> dict:
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
        session_id: str, authorization: Optional[str] = Header(default=None)
    ) -> dict:
        try:
            result = await asyncio.to_thread(
                session_store.complete_cast_session,
                session_id,
                _bearer_token(authorization),
            )
            return jsonable_encoder(result)
        except ExperienceSessionError as error:
            raise _experience_error(error) from error

    @app.post("/v1/pairing-sessions", status_code=201)
    async def create_pairing(body: CastSessionRequest, request: Request) -> dict:
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
                    try:
                        completed = await asyncio.to_thread(
                            session_store.complete_pairing, pairing_id, token
                        )
                    except ExperienceSessionError as error:
                        await websocket.send_json(
                            {"type": "error", "message": str(error)}
                        )
                        continue
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
