from __future__ import annotations

import hashlib
import hmac
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from engine.caster import Caster
from experience.api import create_app
from experience.sessions import ExperienceSessionError, SessionStore


class StubPipeline:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, question: str, casting_input: dict, *, run_id: str) -> dict:
        self.calls.append(
            {"question": question, "casting_input": casting_input, "run_id": run_id}
        )
        cast_result = Caster.cast_manual(casting_input["lines"])
        return {
            "run_id": run_id,
            "cast_result": cast_result,
            "paipan": {
                "name": "测试本卦",
                "changed_hexagram": {"name": "测试变卦"},
                "moving_lines": cast_result["moving_lines"],
                "focus_analysis": {"primary_line": 1, "type": "测试焦点"},
            },
            "interpretation_status": "completed",
            "llm_response": "这是只用于接口测试的受约束解读。",
        }


class ExperienceSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = StubPipeline()
        self.store = SessionStore(pipeline=self.pipeline)

    def test_lines_are_idempotent_auditable_and_complete_once(self) -> None:
        session = self.store.create_cast_session("未来六周应优先关注什么？")
        first = self.store.lock_next_line(
            session["session_id"],
            session["session_token"],
            "first-line",
            motion_energy=72.5,
            trigger_mode="motion",
        )
        duplicate = self.store.lock_next_line(
            session["session_id"],
            session["session_token"],
            "first-line",
            motion_energy=1.0,
            trigger_mode="tap",
        )
        self.assertEqual(first, duplicate)
        self.assertEqual(first["line_count"], 1)
        self.assertEqual(first["line"]["motion_energy"], 72.5)

        for index in range(1, 6):
            self.store.lock_next_line(
                session["session_id"],
                session["session_token"],
                f"line-{index}",
                trigger_mode="tap",
            )
        completed = self.store.complete_cast_session(
            session["session_id"], session["session_token"]
        )
        repeated = self.store.complete_cast_session(
            session["session_id"], session["session_token"]
        )

        self.assertEqual(completed, repeated)
        self.assertEqual(len(self.pipeline.calls), 1)
        self.assertEqual(completed["run_id"], session["run_id"])
        self.assertEqual(
            hashlib.sha256(bytes.fromhex(completed["seed_reveal"])).hexdigest(),
            completed["seed_commitment"],
        )
        seed = bytes.fromhex(completed["seed_reveal"])
        for index, line in enumerate(completed["lines"]):
            digest = hmac.new(
                seed, f"line:{index}".encode("ascii"), hashlib.sha256
            ).digest()
            fronts = sum((digest[0] >> bit) & 1 for bit in range(3))
            self.assertEqual(line["fronts"], fronts)
            self.assertEqual(
                line["value"], Caster.coin_result_to_line(fronts, 3 - fronts)
            )

        submitted = self.pipeline.calls[0]["casting_input"]
        self.assertEqual(
            submitted["lines"],
            list(reversed([line["value"] for line in completed["lines"]])),
        )
        self.assertNotIn("seed_reveal", submitted["experience"])

    def test_invalid_token_incomplete_cast_and_pairing_code_are_rejected(self) -> None:
        session = self.store.create_cast_session("测试问题")
        with self.assertRaises(ExperienceSessionError):
            self.store.lock_next_line(
                session["session_id"], "wrong", "line-1"
            )
        with self.assertRaises(ExperienceSessionError):
            self.store.complete_cast_session(
                session["session_id"], session["session_token"]
            )
        with self.assertRaises(ExperienceSessionError):
            self.store.join_pairing_by_code("000000")

    def test_pairing_code_resolves_same_cast_session(self) -> None:
        pairing = self.store.create_pairing_session("电脑手机协同测试")
        joined = self.store.join_pairing_by_code(pairing["pairing_code"])
        self.assertEqual(joined["pairing_id"], pairing["pairing_id"])
        self.assertEqual(joined["cast_session_id"], pairing["cast_session_id"])
        line = self.store.lock_pairing_line(
            pairing["pairing_id"],
            pairing["pairing_token"],
            "paired-line",
            trigger_mode="motion",
        )
        self.assertEqual(line["line_count"], 1)


class ExperienceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = StubPipeline()
        self.store = SessionStore(pipeline=self.pipeline)
        self.client = TestClient(create_app(self.store))

    def test_static_entries_and_direct_cast_api(self) -> None:
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertIn("手机体感摇卦", self.client.get("/mobile").text)
        self.assertIn("电脑手机协同", self.client.get("/desktop").text)

        created = self.client.post(
            "/v1/cast-sessions", json={"question": "API完整六爻测试"}
        )
        self.assertEqual(created.status_code, 201)
        session = created.json()
        headers = {"Authorization": f"Bearer {session['session_token']}"}
        self.assertEqual(
            self.client.get(
                f"/v1/cast-sessions/{session['session_id']}"
            ).status_code,
            401,
        )

        for index in range(6):
            response = self.client.post(
                f"/v1/cast-sessions/{session['session_id']}/lines",
                headers={**headers, "Idempotency-Key": f"api-line-{index}"},
                json={"trigger_mode": "tap"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["line_count"], index + 1)

        completed = self.client.post(
            f"/v1/cast-sessions/{session['session_id']}/complete",
            headers=headers,
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["status"], "completed")
        self.assertEqual(len(self.pipeline.calls), 1)

    def test_mobile_and_desktop_receive_same_websocket_line(self) -> None:
        with patch.dict(
            "os.environ",
            {"RENDER_EXTERNAL_HOSTNAME": "ai-divination-experience.onrender.com"},
        ):
            response = self.client.post(
                "/v1/pairing-sessions", json={"question": "实时配对测试"}
            )
        created = response.json()
        self.assertTrue(
            created["mobile_url"].startswith(
                "https://ai-divination-experience.onrender.com/mobile?"
            )
        )
        qr = self.client.get(created["qr_url"])
        self.assertEqual(qr.status_code, 200)
        self.assertEqual(qr.headers["content-type"], "image/png")
        self.assertTrue(qr.content.startswith(b"\x89PNG\r\n\x1a\n"))
        base = f"/v1/pairing-sessions/{created['pairing_id']}/ws"
        token = created["pairing_token"]
        with self.client.websocket_connect(
            f"{base}?token={token}&role=desktop"
        ) as desktop:
            desktop_connected = desktop.receive_json()
            self.assertEqual(desktop_connected["type"], "peer_status")
            with self.client.websocket_connect(
                f"{base}?token={token}&role=mobile"
            ) as mobile:
                mobile_seen_by_desktop = desktop.receive_json()
                mobile_self_status = mobile.receive_json()
                self.assertEqual(mobile_seen_by_desktop["role"], "mobile")
                self.assertEqual(mobile_self_status["role"], "mobile")
                mobile.send_json(
                    {
                        "type": "lock_line",
                        "idempotency_key": "ws-line-1",
                        "trigger_mode": "motion",
                        "motion_energy": 66,
                    }
                )
                desktop_line = desktop.receive_json()
                mobile_line = mobile.receive_json()
                self.assertEqual(desktop_line["type"], "line_locked")
                self.assertEqual(desktop_line["line"], mobile_line["line"])


if __name__ == "__main__":
    unittest.main()
