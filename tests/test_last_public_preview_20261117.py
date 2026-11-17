"""Last legal-day public snapshot: survey provenance, timing and model gate."""
import json
import sys
import unittest
from datetime import date,datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from enrich_reviewed_polls import enrich,reviewed_record
from build import paused
from model.polling import match_records
from model.roster import load_roster
from model.data import load_dataset

class LastPublicPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive=json.loads((ROOT/"data/reviewed-additional-polls.json").read_text(encoding="utf8"))
        cls.config=json.loads((ROOT/"config.json").read_text(encoding="utf8"))
        cls.new=[p for p in cls.archive["reports"] if p.get("reviewed_at","").startswith("2026-11-17")]

    def test_publication_safety_margin(self):
        self.assertEqual(self.config["publication_pause_start"],"2026-11-17T19:00:00+08:00")
        self.assertEqual(self.config["publication_pause_end"],"2026-11-28T16:00:00+08:00")
        self.assertFalse(paused(self.config,datetime.fromisoformat("2026-11-17T18:59:59+08:00")))
        self.assertTrue(paused(self.config,datetime.fromisoformat("2026-11-17T19:00:00+08:00")))
        self.assertTrue(paused(self.config,datetime.fromisoformat("2026-11-18T00:00:00+08:00")))
        self.assertFalse(paused(self.config,datetime.fromisoformat("2026-11-28T16:00:00+08:00")))

    def test_reviewed_eight_have_complete_explicit_mass(self):
        self.assertEqual(len(self.new),8)
        keys={(p["pollster_id"],p["county"],p["date"]) for p in self.new}
        self.assertEqual(len(keys),len(self.new))
        for p in self.new:
            with self.subTest(p=p["title"]):
                self.assertGreaterEqual(len(p.get("verification_urls",[])),1)
                self.assertIn("2026",p["published_at"])
                self.assertIn("非",p["sample_note"]+"非")  # free-text limitations must exist
                self.assertGreater(len(p["sample_note"]),60)
                self.assertEqual(p["confidence_level"],95)
                d=reviewed_record(p,p["reviewed_at"],date(2026,11,17))
                self.assertAlmostEqual(sum(c["support"] for c in d["candidates"])+d["undecided"]+d["nonvote"]+d["response_mass_unreported"],100,delta=1)
                self.assertTrue(d["source_url"].startswith("https://"))
                if d["commissioning_type"]=="external_commissioned":
                    self.assertTrue(d["commissioner_id"])

    def test_pre_publication_snapshots_do_not_read_future_revisions(self):
        base={"records":[],"sources":[],"polls":[],"history":[],"failures":[],"source_review":[],"checked_at":"2026-11-17T05:00:00+00:00"}
        prev=enrich(base,self.config,self.archive,date(2026,11,16))
        self.assertFalse(any(r.get("retrieved_at","").startswith("2026-11-17") for r in prev["records"]))
        now=enrich(base,self.config,self.archive,date(2026,11,17))
        got=[r for r in now["records"] if r.get("retrieved_at","").startswith("2026-11-17")]
        self.assertEqual(len(got),8)
        self.assertEqual(now["latest_fieldwork_date"],"2026-11-15")
        self.assertEqual(len({r["id"] for r in got}),len(got))
        self.assertEqual(enrich(now,self.config,self.archive,date(2026,11,17))["records"],now["records"])

    def test_all_eight_match_roster_in_isolation(self):
        history=load_dataset(ROOT/"data/candidate-history-cec.json")
        roster=load_roster(ROOT/"data/registration-roster-2026.json",history)
        for p in self.new:
            with self.subTest(p=p["title"]):
                row=reviewed_record(p,p["reviewed_at"],date(2026,11,17))
                accepted,audit=match_records({"records":[row]},roster,"2026-11-17")
                self.assertEqual(len(accepted),1,str(audit))
                self.assertTrue(audit[0]["included"])

if __name__=="__main__":
    unittest.main()
