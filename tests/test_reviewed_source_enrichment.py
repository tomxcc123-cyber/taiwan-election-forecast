import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from enrich_reviewed_polls import enrich, reviewed_record


class ReviewedSourceEnrichmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        cls.reviewed = json.loads((ROOT / "data/reviewed-additional-polls.json").read_text(encoding="utf-8"))

    def base_feed(self):
        return {
            "schema_version": 1,
            "checked_at": "2026-09-12T07:00:00+00:00",
            "updated_at": "2026-09-12T06:30:00+00:00",
            "latest_fieldwork_date": "2026-08-30",
            "status": "degraded",
            "baseline_cutoff": self.config["baseline_cutoff"],
            "sources": [
                {
                    "name": "ETtoday 民調雲",
                    "url": "https://feeds.feedburner.com/ettoday/newslist",
                    "validated_reports": 0,
                    "reviewed_reports": 2,
                    "status": "checked",
                }
            ],
            "source_review": [
                {
                    "name": "ETtoday",
                    "status": "integrated_with_reviewed_seed_and_live_discovery",
                    "note": "already integrated",
                    "url": "https://www.ettoday.net/",
                },
                {
                    "name": "聯合報",
                    "status": "reviewed_not_integrated",
                    "note": "old note",
                    "url": "https://udn.com/",
                },
                {
                    "name": "中時／艾普羅",
                    "status": "access_limited",
                    "note": "old note",
                    "url": "https://www.chinatimes.com/",
                },
            ],
            "discovery_queue": [],
            "records": [],
            "polls": [],
            "failures": [],
            "reports": {},
            "history": [],
            "coverage_note": "來源包括TVBS、美麗島與ETtoday民調雲。",
        }

    def test_trend_seed_is_complete_and_current_matchup_is_eligible(self):
        entry = self.reviewed["reports"][0]
        row = reviewed_record(entry, self.reviewed["reviewed_at"], date(2026, 9, 12))
        self.assertEqual(row["pollster_id"], "trend-survey")
        self.assertAlmostEqual(sum(c["support"] for c in row["candidates"]) + row["undecided"] + row["nonvote"], 100.0)
        result = enrich(self.base_feed(), self.config, self.reviewed, date(2026, 9, 12))
        trend = [r for r in result["records"] if r.get("pollster_id") == "trend-survey"]
        self.assertEqual(len(trend), 1)
        self.assertTrue(trend[0]["model_eligible"])
        self.assertIsNone(trend[0]["exclusion_reason"])
        model_rows = [r for r in result["polls"] if r.get("pollster_id") == "trend-survey"]
        self.assertEqual(len(model_rows), 1)
        self.assertEqual(model_rows[0]["county"], "台中市")
        self.assertEqual(model_rows[0]["blue"], 42.8)
        self.assertEqual(model_rows[0]["dpp"], 36.1)
        self.assertEqual(model_rows[0]["undecided"], 21.1)

    def test_integrated_source_is_not_left_in_source_review(self):
        result = enrich(self.base_feed(), self.config, self.reviewed, date(2026, 9, 12))
        names = {r["name"] for r in result["source_review"]}
        self.assertNotIn("ETtoday", names)
        self.assertIn("艾普羅行銷市場研究", names)
        self.assertIn("聯合報", names)
        self.assertFalse(any(str(r.get("status", "")).startswith("integrated_") for r in result["source_review"]))

    def test_apollo_stays_fail_closed_and_out_of_records(self):
        result = enrich(self.base_feed(), self.config, self.reviewed, date(2026, 9, 12))
        self.assertFalse(any(r.get("pollster_id") == "apollo" for r in result["records"]))
        apollo = next(r for r in result["source_review"] if r["name"] == "艾普羅行銷市場研究")
        self.assertEqual(apollo["status"], "reviewed_methodology_incomplete_response_mass")
        self.assertIn("不以剩餘比例自行補成未表態", apollo["note"])

    def test_automatic_record_takes_precedence_over_reviewed_seed(self):
        entry = self.reviewed["reports"][0]
        auto = reviewed_record(entry, self.reviewed["reviewed_at"], date(2026, 9, 12))
        auto["id"] = "automatic-trend-test"
        auto["ingestion"] = "automatic_original_html"
        auto["retrieved_at"] = "2026-09-12T07:00:00+00:00"
        feed = self.base_feed()
        feed["records"] = [copy.deepcopy(auto)]
        result = enrich(feed, self.config, self.reviewed, date(2026, 9, 12))
        same = [r for r in result["records"] if r.get("pollster_id") == "trend-survey" and r["county"] == "台中市"]
        self.assertEqual(len(same), 1)
        self.assertEqual(same[0]["id"], "automatic-trend-test")
        self.assertEqual(same[0]["ingestion"], "automatic_original_html")

    def test_enrichment_is_idempotent(self):
        once = enrich(self.base_feed(), self.config, self.reviewed, date(2026, 9, 12))
        twice = enrich(once, self.config, self.reviewed, date(2026, 9, 12))
        self.assertEqual(once["records"], twice["records"])
        self.assertEqual(once["polls"], twice["polls"])
        self.assertEqual(once["source_review"], twice["source_review"])
        self.assertEqual(len([s for s in twice["sources"] if s["name"] == "新台灣國策智庫／趨勢民調"]), 1)


if __name__ == "__main__":
    unittest.main()
