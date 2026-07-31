import hashlib
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from engine.astronomy import AstronomyCalculationError, AstronomyService
from engine.caster import Caster, CastingError
from engine.guardrails import Guardrails
from engine.llm_interpreter import LLMInterpreter
from engine.paipan import PaipanEngine, PaipanError


ROOT = Path(__file__).resolve().parents[1]


class HexagramDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = ROOT / "data" / "hexagrams_db.json"
        cls.db = json.loads(cls.db_path.read_text(encoding="utf-8"))

    def test_database_covers_all_hexagrams_and_lines(self):
        self.assertEqual(len(self.db), 64)
        self.assertEqual(set(self.db), {f"{value:06b}" for value in range(64)})
        self.assertEqual(
            sorted(item["king_wen_number"] for item in self.db.values()),
            list(range(1, 65)),
        )
        self.assertEqual(sum(len(item["lines"]) for item in self.db.values()), 384)
        self.assertEqual(len({item["symbol"] for item in self.db.values()}), 64)
        self.assertEqual(
            {code for code, item in self.db.items() if item["special_line"]},
            {"111111", "000000"},
        )

    def test_every_rule_record_is_complete(self):
        palace_counts = {}
        for code, item in self.db.items():
            palace_counts[item["palace_name"]] = palace_counts.get(item["palace_name"], 0) + 1
            self.assertTrue(item["judgement"], code)
            self.assertTrue(item["tuan"], code)
            self.assertTrue(item["image"], code)
            self.assertEqual(set(item["lines"]), {str(value) for value in range(1, 7)})
            self.assertEqual(len(item["najia"]), 6)
            self.assertGreater(item["source"]["revision_id"], 0)
            self.assertTrue(item["source"]["revision_timestamp"])
            self.assertTrue(item["source"]["url"].startswith("https://zh.wikisource.org/wiki/"))
            self.assertEqual(
                [number for number in range(1, 7) if item["lines"][str(number)]["is_shi"]],
                [item["shi"]],
            )
            self.assertEqual(
                [number for number in range(1, 7) if item["lines"][str(number)]["is_ying"]],
                [item["ying"]],
            )
            for number, line in item["lines"].items():
                self.assertTrue(line["text"], (code, number))
                self.assertTrue(line["image"], (code, number))
                self.assertIn(line["relative"], {"父母", "官鬼", "妻财", "兄弟", "子孙"})
        self.assertEqual(set(palace_counts.values()), {8})

    def test_classic_and_rule_anchors(self):
        qian = self.db["111111"]
        kun = self.db["000000"]
        zhun = self.db["100010"]
        dayou = self.db["111101"]
        self.assertEqual((qian["king_wen_number"], qian["symbol"], qian["name"]), (1, "䷀", "乾为天"))
        self.assertEqual(qian["najia"], ["甲子", "甲寅", "甲辰", "壬午", "壬申", "壬戌"])
        self.assertEqual(qian["special_line"]["line_name"], "用九")
        self.assertIn("見羣龍无首", qian["special_line"]["text"])
        self.assertEqual(kun["special_line"]["line_name"], "用六")
        self.assertEqual((zhun["king_wen_number"], zhun["name"], zhun["shi"], zhun["ying"]), (3, "水雷屯", 2, 5))
        self.assertIn("磐桓", zhun["lines"]["1"]["text"])
        self.assertIn("大車以載", dayou["lines"]["2"]["text"])

    def test_all_eight_palace_sequences_match_reference_table(self):
        expected = {
            "乾": ["乾为天", "天风姤", "天山遁", "天地否", "风地观", "山地剥", "火地晋", "火天大有"],
            "坎": ["坎为水", "水泽节", "水雷屯", "水火既济", "泽火革", "雷火丰", "地火明夷", "地水师"],
            "艮": ["艮为山", "山火贲", "山天大畜", "山泽损", "火泽睽", "天泽履", "风泽中孚", "风山渐"],
            "震": ["震为雷", "雷地豫", "雷水解", "雷风恒", "地风升", "水风井", "泽风大过", "泽雷随"],
            "巽": ["巽为风", "风天小畜", "风火家人", "风雷益", "天雷无妄", "火雷噬嗑", "山雷颐", "山风蛊"],
            "离": ["离为火", "火山旅", "火风鼎", "火水未济", "山水蒙", "风水涣", "天水讼", "天火同人"],
            "坤": ["坤为地", "地雷复", "地泽临", "地天泰", "雷天大壮", "泽天夬", "水天需", "水地比"],
            "兑": ["兑为泽", "泽水困", "泽地萃", "泽山咸", "水山蹇", "地山谦", "雷山小过", "雷泽归妹"],
        }
        positions = ["本宫", "一世", "二世", "三世", "四世", "五世", "游魂", "归魂"]
        by_name = {item["name"]: item for item in self.db.values()}
        for palace, names in expected.items():
            for position, name in zip(positions, names):
                self.assertEqual(by_name[name]["palace_name"], palace, name)
                self.assertEqual(by_name[name]["palace_position"], position, name)

    def test_metadata_hash_matches_database(self):
        metadata = json.loads((ROOT / "data" / "hexagrams_db.meta.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["record_count"], 64)
        self.assertEqual(
            metadata["sha256"],
            hashlib.sha256(self.db_path.read_bytes()).hexdigest(),
        )


class CalendarTests(unittest.TestCase):
    def test_four_pillars_match_verified_reference_case(self):
        result = AstronomyService.get_ganzhi_calendar(datetime(2026, 8, 12, 10, 30), 120.0)
        self.assertEqual(result["four_pillars"], ["丙午", "丙申", "戊午", "丁巳"])
        self.assertEqual(result["xunkong"], ["子", "丑"])
        self.assertEqual(result["liushen"], ["勾陈", "螣蛇", "白虎", "玄武", "青龙", "朱雀"])

    def test_lichun_boundary_uses_exact_instant_not_whole_day(self):
        before = AstronomyService.get_ganzhi_calendar(datetime(2024, 2, 4, 16, 20), 120.0)
        after = AstronomyService.get_ganzhi_calendar(datetime(2024, 2, 4, 16, 30), 120.0)
        self.assertEqual(before["four_pillars"][:2], ["癸卯", "乙丑"])
        self.assertEqual(after["four_pillars"][:2], ["甲辰", "丙寅"])
        self.assertEqual(after["current_solar_term"]["name"], "立春")

    def test_aware_datetime_uses_same_absolute_solar_term_boundary(self):
        utc_time = datetime(2024, 2, 4, 8, 30, tzinfo=timezone.utc)
        result = AstronomyService.get_ganzhi_calendar(utc_time, 0.0, 51.5, 0.0)
        self.assertEqual(result["beijing_reference_time"], "2024-02-04T16:30:00.000")
        self.assertEqual(result["four_pillars"][:2], ["甲辰", "丙寅"])

    def test_true_solar_time_uses_longitude_and_equation_of_time(self):
        result = AstronomyService.get_ganzhi_calendar(
            datetime(2026, 8, 12, 10, 30), 87.6, 43.8, 8.0
        )
        correction = datetime.fromisoformat(result["true_solar_time"]) - datetime(2026, 8, 12, 10, 30)
        expected_minutes = result["longitude_correction_minutes"] + result["equation_of_time_minutes"]
        self.assertAlmostEqual(correction.total_seconds() / 60, expected_minutes, places=3)
        self.assertEqual(result["longitude_correction_minutes"], -129.6)

    def test_calendar_matches_independent_lunar_python(self):
        try:
            from lunar_python import Solar
        except ImportError:
            self.skipTest("lunar-python is an optional verification dependency")
        reference = Solar.fromYmdHms(2026, 8, 12, 10, 30, 0).getLunar().getEightChar()
        expected = [reference.getYear(), reference.getMonth(), reference.getDay(), reference.getTime()]
        actual = AstronomyService.get_ganzhi_calendar(datetime(2026, 8, 12, 10, 30), 120.0)
        self.assertEqual(actual["four_pillars"], expected)

    def test_invalid_coordinates_are_rejected(self):
        with self.assertRaises(AstronomyCalculationError):
            AstronomyService.get_ganzhi_calendar(datetime.now(), 181)
        with self.assertRaises(AstronomyCalculationError):
            AstronomyService.get_ganzhi_calendar(datetime.now(), 120, -91)

    def test_calendar_calculation_stays_under_latency_budget(self):
        started = time.perf_counter()
        for _ in range(20):
            AstronomyService.get_ganzhi_calendar(datetime(2026, 8, 12, 10, 30), 120.0)
        average_ms = (time.perf_counter() - started) * 1000 / 20
        self.assertLess(average_ms, 150)


class CasterTests(unittest.TestCase):
    def test_manual_cast_builds_actual_hexagram_code(self):
        result = Caster.cast_manual([8, 8, 8, 8, 8, 8])
        self.assertEqual(result["hexagram_code"], "000000")
        self.assertIsNone(result["changed_hexagram_code"])
        self.assertEqual(result["moving_lines"], [])

    def test_number_cast_combines_lower_and_upper_trigrams(self):
        result = Caster.cast_number([1, 8, 6])
        self.assertEqual(result["hexagram_code"], "000111")
        self.assertEqual(result["changed_hexagram_code"], "000110")
        self.assertEqual(result["moving_lines"], [6])

    def test_boolean_is_not_accepted_as_an_integer(self):
        with self.assertRaises(CastingError):
            Caster.cast_number([True, 1, 1])


class PipelineComponentTests(unittest.TestCase):
    def setUp(self):
        self.calendar = AstronomyService.get_ganzhi_calendar(datetime(2026, 7, 31, 12), 120.0)
        self.engine = PaipanEngine()

    def test_static_kun_cast_uses_kun_repository_record(self):
        paipan = self.engine.build_paipan(Caster.cast_manual([8, 8, 8, 8, 8, 8]), self.calendar)
        self.assertEqual(paipan["name"], "坤为地")
        self.assertTrue(Guardrails.validate_paipan_data(paipan))

    def test_all_sixty_four_codes_resolve(self):
        for value in range(64):
            code = f"{value:06b}"
            cast = {"hexagram_code": code, "changed_hexagram_code": None, "moving_lines": []}
            self.assertTrue(Guardrails.validate_paipan_data(self.engine.build_paipan(cast, self.calendar)))

    def test_missing_classic_data_stops_instead_of_faking_a_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "db.json"
            path.write_text(json.dumps({"000000": self.engine.db["000000"]}), encoding="utf-8")
            limited = PaipanEngine(path)
            with self.assertRaises(PaipanError):
                limited.build_paipan(Caster.cast_number([1, 8, 6]), self.calendar)

    def test_qian_all_moving_uses_special_line(self):
        paipan = self.engine.build_paipan(Caster.cast_manual([9, 9, 9, 9, 9, 9]), self.calendar)
        self.assertTrue(Guardrails.validate_paipan_data(paipan))
        self.assertEqual(paipan["focus_analysis"]["primary_focus"], None)
        self.assertEqual(paipan["focus_text"]["line_name"], "用九")
        self.assertEqual(paipan["changed_hexagram"]["name"], "坤为地")

    def test_line_calendar_statuses_are_deterministic_booleans(self):
        paipan = self.engine.build_paipan(Caster.cast_manual([8, 8, 8, 8, 8, 8]), self.calendar)
        for line in paipan["lines_detail"].values():
            for field in ("is_xunkong", "is_month_break", "is_day_clash", "is_wood_tomb"):
                self.assertIs(type(line[field]), bool)

    def test_mock_interpreter_returns_complete_disclaimer(self):
        context = {
            "user_query": "测试问题",
            "paipan_summary": {
                "卦名": "坤为地",
                "宫位": "坤土",
                "干支": "甲子",
                "焦点爻": {
                    "primary_focus": 6,
                    "type": "静卦世爻",
                    "description": "本局为静卦，以世爻为核心焦点。",
                },
                "卦辞原典": "坤：元，亨，利牝马之贞。",
                "焦点爻辞": {"line_name": "上六", "text": "龙战于野，其血玄黄。"},
            },
        }
        response = LLMInterpreter().interpret(context)
        self.assertIn("【免责声明】", response)
        self.assertIn("坤为地", response)


if __name__ == "__main__":
    unittest.main()
