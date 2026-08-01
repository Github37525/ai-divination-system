import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MINIPROGRAM = ROOT / "miniprogram"


class MiniProgramStructureTests(unittest.TestCase):
    def test_manifest_declares_cast_and_history_pages(self) -> None:
        manifest = json.loads((MINIPROGRAM / "app.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["pages"],
            ["pages/index/index", "pages/history/history"],
        )
        for page in manifest["pages"]:
            for suffix in (".js", ".json", ".wxml", ".wxss"):
                self.assertTrue((MINIPROGRAM / f"{page}{suffix}").exists())

    def test_client_uses_production_api_without_embedding_model_secret(self) -> None:
        app_source = (MINIPROGRAM / "app.js").read_text(encoding="utf-8")
        api_source = (MINIPROGRAM / "utils" / "api.js").read_text(encoding="utf-8")
        all_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in MINIPROGRAM.rglob("*")
            if path.is_file()
        )
        self.assertIn("https://ai-divination-experience.onrender.com", app_source)
        self.assertIn("/v1/cast-sessions", api_source)
        self.assertIn('headers.Authorization = `Bearer ${options.token}`', api_source)
        self.assertNotIn("DEEPSEEK_API_KEY", all_source)
        self.assertNotRegex(all_source, r"sk-[A-Za-z0-9]{12,}")

    def test_cast_page_supports_motion_haptics_resume_and_async_result(self) -> None:
        source = (MINIPROGRAM / "pages" / "index" / "index.js").read_text(
            encoding="utf-8"
        )
        for marker in (
            "wx.startAccelerometer",
            "wx.onAccelerometerChange",
            "wx.vibrateShort",
            "restoreSession",
            "interpretation_pending",
            "schedulePoll",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
