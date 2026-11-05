"""Symmetric sponsor-uncertainty tests; all poll results here are synthetic."""
import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np

from model.joint import SETTINGS, infer
from model.commissioner_audit import build_commissioner_audit
from model.polling import day
from model.roster import load_roster
from model.data import load_dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from enrich_reviewed_polls import enrich, reviewed_record


def dummy_prior():
    race = {
        "race_id": "synthetic-race",
        "county": "synthetic-county",
        "region": "synthetic-region",
        "candidates": [
            {"candidate_id": "a", "party": "KMT"},
            {"candidate_id": "b", "party": "DPP"},
        ],
    }
    p = np.linspace(.24, .76, 300)
    return {"races": [race], "shares": {"synthetic-race": np.column_stack([p, 1-p])}}


def dummy_row(a=60, commissioner="synthetic-commissioner", pollster="synthetic-firm", date_string="2026-10-30"):
    return {
        "id": f"test-{pollster}-{date_string}",
        "race_id": "synthetic-race",
        "county": "synthetic-county",
        "source": pollster,
        "pollster_id": pollster,
        "sample_n": 1077,
        "field_start": date_string,
        "date": date_string,
        "field_mid": day(date_string),
        "candidate_ids": ["a", "b"],
        "supports": [a, 100-a],
        "undecided": 0.0,
        "nonvote": 0.0,
        "response_mass_unreported": 0.0,
        "partial_ballot": False,
        "commissioning_type": "external_commissioned" if commissioner else "in_house",
        "commissioner_id": commissioner,
    }


def posterior(rows, sponsor_sd=.20, **kwargs):
    return infer(dummy_prior(), rows, "2026-11-05", "2026-11-05",
                 {"commissioned_house_sd": sponsor_sd, "simulations": 40, **kwargs})


class CommissionerWeightingTests(unittest.TestCase):
    def test_no_assumed_pro_blue_or_pro_green_bias(self):
        positive = posterior([dummy_row(60)], .20)
        negative = posterior([dummy_row(40)], .20)
        self.assertAlmostEqual(positive["mean"][0], -negative["mean"][0], places=8)
        self.assertAlmostEqual(positive["mean"][1], -negative["mean"][1], places=8)
        self.assertEqual(positive["diagnostics"]["commissioned_reports"], 1)
        self.assertEqual(positive["diagnostics"]["commissioning_groups"], 1)

    def test_more_uncertainty_reduces_single_commissioned_poll_influence(self):
        base = posterior([dummy_row(60)], 0)
        cautious = posterior([dummy_row(60)], .20)
        self.assertGreater(np.linalg.norm(base["mean"]), np.linalg.norm(cautious["mean"]))
        self.assertGreater(np.trace(cautious["current_covariance"]), np.trace(base["current_covariance"]))

    def test_inhouse_polls_unchanged(self):
        sample = dummy_row(60, commissioner=None)
        no_penalty = posterior([sample], 0)
        with_penalty = posterior([sample], .20)
        np.testing.assert_allclose(no_penalty["mean"], with_penalty["mean"], atol=1e-11)
        np.testing.assert_allclose(no_penalty["current_covariance"], with_penalty["current_covariance"], atol=1e-11)

    def test_commissioner_waves_are_not_independent(self):
        row1 = dummy_row(60, commissioner="sponsor1", pollster="firm1", date_string="2026-10-27")
        row2 = dummy_row(60, commissioner="sponsor1", pollster="firm2", date_string="2026-10-30")
        shared = posterior([row1, row2], .20, house_sd=0.0)
        independent = posterior([row1, {**row2, "commissioner_id": "sponsor2"}], .20, house_sd=0.0)
        self.assertLess(np.linalg.norm(shared["mean"]), np.linalg.norm(independent["mean"]))

    def test_read_only_leave_one_commissioner_out_is_a_sensitivity_not_bias(self):
        rows = [dummy_row(60)]
        current = posterior(rows, .20)
        original_mean = current["mean"].copy()
        result = build_commissioner_audit(dummy_prior(), rows, current,
                                          "2026-11-05", "2026-11-05")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["affects_formal_forecast"])
        self.assertTrue(result["not_partisan_bias_estimate"])
        self.assertEqual(result["commissioner_group_count"], 1)
        group = result["leave_one_commissioner_out"][0]
        self.assertEqual(group["commissioner_id"], "synthetic-commissioner")
        self.assertEqual(group["report_count"], 1)
        self.assertEqual(len(group["counties"]), 1)
        self.assertGreater(group["counties"][0]["max_abs_shift_pp"], 0)
        self.assertGreater(result["without_commissioner_variance"][0]["max_abs_shift_pp"], 0)
        np.testing.assert_allclose(current["mean"], original_mean)
        opposite = posterior([dummy_row(40)], .20)
        inverse = build_commissioner_audit(dummy_prior(), [dummy_row(40)], opposite,
                                           "2026-11-05", "2026-11-05")
        # Fixed finite Monte Carlo draws need not give exactly equal shift
        # magnitudes when a single source is removed, even with symmetric
        # analytical posterior means. The no-direction gate above checks means.
        self.assertEqual(inverse["leave_one_commissioner_out"][0]["commissioner_id"],
                         "synthetic-commissioner")
        self.assertGreater(inverse["leave_one_commissioner_out"][0]["counties"][0]["max_abs_shift_pp"], 0)

    def test_missing_commissioner_is_not_silently_treated_as_inhouse(self):
        bad = dummy_row(60)
        bad.pop("commissioner_id")
        with self.assertRaisesRegex(ValueError, "commissioner ID"):
            posterior([bad])

    def test_real_seed_metadata_and_time_cutoff(self):
        archive = json.loads((ROOT / "data/reviewed-additional-polls.json").read_text(encoding="utf8"))
        config = json.loads((ROOT / "config.json").read_text(encoding="utf8"))
        base = {"records": [], "polls": [], "sources": [], "source_review": [], "history": [],
                "failures": [], "checked_at": "2026-11-05T09:00:00+00:00"}
        now = enrich(base, config, archive, date(2026, 11, 5))
        rows = [r for r in now["records"] if r["county"] == "台中市"]
        by_source = {r["pollster_id"]: r for r in rows}
        self.assertEqual(by_source["formosa-bic"]["commissioning_type"], "external_commissioned")
        self.assertEqual(by_source["formosa-bic"]["commissioner_id"], "xinmin-association")
        self.assertEqual(by_source["trend-survey"]["commissioning_type"], "external_commissioned")
        self.assertEqual(by_source["trend-survey"]["commissioner_id"], "ketagalan-foundation")
        self.assertEqual(next(r for r in now["records"] if r["pollster_id"] == "tvbs")["commissioning_type"], "in_house")
        early = enrich(base, config, archive, date(2026, 11, 2))
        self.assertFalse(any(r["commissioner_id"] == "xinmin-association"
                             for r in early["records"] if r.get("commissioner_id")))


if __name__ == "__main__":
    unittest.main()
