import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class StreamlitSmokeTests(unittest.TestCase):
    def test_app_executes_without_import_or_render_exception(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
        self.assertEqual(list(app.exception), [])


if __name__ == "__main__":
    unittest.main()
