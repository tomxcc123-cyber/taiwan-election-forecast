"""Regression gates for November 5, 2026 poll catch-up.

Data are checked as published measurements. Tests must not infer elections
or manufacture responses to force a total of 100 percent.
"""
import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from enrich_reviewed_polls import enrich, reviewed_record

class PollCatchupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        cls.archive = json.loads((ROOT / "data/reviewed-additional-polls.json").read_text(encoding="utf-8"))
        cls.new_rows = [p for p in cls.archive["reports"] if p.get("reviewed_at", "").startswith("2026-11-05") and p["pollster_id"] in ("tvbs", "ettoday")]
        cls.tvbs = next(p for p in cls.new_rows if p["pollster_id"] == "tvbs")
        cls.ettoday = next(p for p in cls.new_rows if p["pollster_id"] == "ettoday")

    def test_source_provenance_and_partial_response(self):
        self.assertEqual(len(self.new_rows), 2)
        self.assertEqual(self.tvbs["date"], "2026-10-31")
        self.assertEqual(self.tvbs["sample_n"], 1666)
        self.assertEqual(self.tvbs["supports"], [46, 42])
        self.assertIn("tvbs.com.tw", self.tvbs["source_url"])
        self.assertEqual(self.ettoday["date"], "2026-11-01")
        self.assertEqual(self.ettoday["sample_n"], 1965)
        self.assertEqual(self.ettoday["supports"], [52, 40.7])
        self.assertEqual(self.ettoday["response_mass_unreported"], 0.5)
        for entry in self.new_rows:
            self.assertGreaterEqual(len(entry.get("verification_urls", [])), 1)
            row = reviewed_record(entry, entry["reviewed_at"], date(2026, 11, 5))
            self.assertEqual(len(row["candidates"]), 2)
            self.assertEqual(row["date"], entry["date"])
            measured = sum(c["support"] for c in row["candidates"])
            measured += row["undecided"] + row["nonvote"] + row["response_mass_unreported"]
            self.assertLessEqual(abs(measured - 100), 1.0)

    def test_backdated_analysis_cannot_see_november_review(self):
        base = {"records": [], "sources": [], "polls": [], "failures": [], "source_review": [],
                "history": [], "checked_at": "2026-11-02T00:00:00+00:00"}
        old = enrich(copy.deepcopy(base), self.config, self.archive, date(2026, 11, 2))
        self.assertFalse(any(r.get("id") == reviewed_record(
            e, e["reviewed_at"], date(2026, 11, 5))["id"] for r in old["records"] for e in self.new_rows))
        current = enrich(copy.deepcopy(base), self.config, self.archive, date(2026, 11, 5))
        seen = {(r["pollster_id"], r["county"], r["date"]) for r in current["records"]}
        self.assertIn(("tvbs", "台北市", "2026-10-31"), seen)
        self.assertIn(("ettoday", "台北市", "2026-11-01"), seen)
        self.assertEqual(enrich(current, self.config, self.archive, date(2026, 11, 5))["records"],
                         current["records"])
        by_source = [r for r in current["records"]
                     if r.get("pollster_id") in ("tvbs", "ettoday") and r.get("county") == "台北市"
                     and r["date"] >= "2026-10-31"]
        self.assertEqual(len(by_source), 2)

if __name__ == "__main__":
    unittest.main()
