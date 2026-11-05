"""Primary-source 2026 Taichung poll review and candidate-observation gate."""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from enrich_reviewed_polls import reviewed_record,enrich
from model.polling import match_records
from model.data import load_dataset
from model.roster import load_roster

class TaichungPrimarySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((ROOT/"config.json").read_text(encoding="utf8"))
        cls.archive=json.loads((ROOT/"data/reviewed-additional-polls.json").read_text(encoding="utf8"))
        cls.seed=next(e for e in cls.archive["reports"] if e["county"]=="台中市" and e.get("pollster_id")=="formosa-bic" and e["date"]=="2026-10-30")

    def base_feed(self):
        return {"checked_at":"2026-11-05T09:00:00+00:00","records":[],"polls":[],"sources":[],
                "source_review":[],"failures":[],"discovery_queue":[],"history":[]}

    def test_original_pdf_complete_response_and_method(self):
        s=self.seed
        self.assertEqual(s["source_url"],"https://dc579968-5ed9-4902-8454-9871fa44324e.filesusr.com/ugd/3ea6ac_0b4a9fd7880b4b5589bd8f2b4ecc627a.pdf")
        self.assertEqual((s["sample_n"],s["published_at"]),(1077,"2026-11-03"))
        self.assertEqual((s["field_start"],s["date"]),("2026-10-28","2026-10-30"))
        self.assertEqual(s["method_class"],"dual_frame_cati")
        self.assertIn("教育",s["weighting"])
        self.assertEqual(set(s["names"]),{"江啟臣","何欣純","洪麗華"})
        self.assertAlmostEqual(sum(s["supports"])+s["undecided"]+s["nonvote"],100)
        row=reviewed_record(s,s["reviewed_at"],date(2026,11,5))
        self.assertEqual(row["pollster_id"],"formosa-bic")
        self.assertEqual(len(row["candidates"]),3)
        self.assertEqual(row["response_mass_unreported"],0.0)
        self.assertFalse(row["nonvote_reported"] is False)

    def test_temporal_holdout_and_candidate_model_eligibility(self):
        early=enrich(self.base_feed(),self.config,self.archive,date(2026,11,2))
        self.assertFalse(any(r.get("pollster_id")=="formosa-bic" and r.get("county")=="台中市" and r.get("date")=="2026-10-30" for r in early["records"]))
        current=enrich(self.base_feed(),self.config,self.archive,date(2026,11,5))
        matched=[r for r in current["records"] if r.get("pollster_id")=="formosa-bic" and r.get("county")=="台中市" and r.get("date")=="2026-10-30"]
        self.assertEqual(len(matched),1)
        self.assertFalse(matched[0]["model_eligible"])  # Legacy three-bloc system cannot model separate nonvoters.
        hist=load_dataset(ROOT/"data/candidate-history-cec.json")
        roster=load_roster(ROOT/"data/registration-roster-2026.json",hist)
        accepted,audit=match_records({"records":[matched[0]]},roster,"2026-11-05")
        self.assertEqual(len(accepted),1)  # Candidate research likelihood retains the full three-candidate response.
        self.assertEqual(len(accepted[0]["candidate_ids"]),3)
        self.assertEqual(accepted[0]["nonvote"],7.0)
        self.assertTrue(audit[0]["included"])
        self.assertEqual(enrich(current,self.config,self.archive,date(2026,11,5))["records"],current["records"])

if __name__=="__main__":
    unittest.main()
