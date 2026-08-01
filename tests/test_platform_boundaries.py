import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CULTURE_APP = ROOT / "miniprogram-culture"
INTERNAL_APP = ROOT / "miniprogram"


def generated_records() -> tuple[str, list[dict]]:
    source = (CULTURE_APP / "data" / "hexagrams.js").read_text(encoding="utf-8")
    match = re.search(
        r"const HEXAGRAMS = (\[.*\]);\n\nmodule\.exports",
        source,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError("文化版数据包格式不合法")
    hash_match = re.search(r'DATABASE_SHA256: "([0-9a-f]{64})"', source)
    if not hash_match:
        raise AssertionError("文化版数据包缺少数据库哈希")
    return hash_match.group(1), json.loads(match.group(1))


class PublicCultureMiniProgramTests(unittest.TestCase):
    def test_public_package_has_only_learning_pages(self) -> None:
        manifest = json.loads((CULTURE_APP / "app.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["pages"],
            [
                "pages/library/library",
                "pages/detail/detail",
                "pages/glossary/glossary",
                "pages/about/about",
            ],
        )
        for page in manifest["pages"]:
            for suffix in (".js", ".json", ".wxml", ".wxss"):
                self.assertTrue((CULTURE_APP / f"{page}{suffix}").exists())

    def test_public_package_contains_complete_verified_classics(self) -> None:
        database_hash, records = generated_records()
        database = json.loads(
            (ROOT / "data" / "hexagrams_db.json").read_text(encoding="utf-8")
        )
        metadata = json.loads(
            (ROOT / "data" / "hexagrams_db.meta.json").read_text(encoding="utf-8")
        )
        self.assertEqual(database_hash, metadata["sha256"])
        self.assertEqual(len(records), 64)
        self.assertEqual(sum(len(record["lines"]) for record in records), 384)
        self.assertEqual(sum(record["specialLine"] is not None for record in records), 2)
        self.assertEqual([record["number"] for record in records], list(range(1, 65)))
        for record in records:
            source = database[record["code"]]
            self.assertEqual(record["displayNumber"], f'{record["number"]:02d}')
            self.assertEqual(record["name"], source["name"])
            self.assertEqual(record["judgement"], source["judgement"])
            self.assertEqual(record["tuan"], source["tuan"])
            self.assertEqual(record["image"], source["image"])
            self.assertEqual(
                [line["text"] for line in record["lines"]],
                [source["lines"][str(index)]["text"] for index in range(1, 7)],
            )

    def test_public_package_cannot_call_interactive_experience(self) -> None:
        application_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in CULTURE_APP.rglob("*")
            if path.is_file()
            and path.suffix in {".js", ".json", ".wxml"}
            and path.name != "hexagrams.js"
        )
        forbidden_markers = (
            "wx.request",
            "wx.connectSocket",
            "startAccelerometer",
            "onAccelerometerChange",
            "vibrateShort",
            "vibrateLong",
            "/v1/cast-sessions",
            "DEEPSEEK",
            "DeepSeek",
            "<textarea",
            "<web-view",
        )
        for marker in forbidden_markers:
            self.assertNotIn(marker, application_source)

    def test_internal_experience_is_visibly_separated(self) -> None:
        project = json.loads(
            (INTERNAL_APP / "project.config.json").read_text(encoding="utf-8")
        )
        readme = (INTERNAL_APP / "README.md").read_text(encoding="utf-8")
        page = (INTERNAL_APP / "pages" / "index" / "index.wxml").read_text(
            encoding="utf-8"
        )
        self.assertIn("internal-lab", project["projectname"])
        self.assertIn("不提交公开审核", readme)
        self.assertIn("不用于公开提审", page)


if __name__ == "__main__":
    unittest.main()
