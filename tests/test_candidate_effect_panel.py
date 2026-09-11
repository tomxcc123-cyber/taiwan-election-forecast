import unittest

from model.candidate_effect_panel import build_panel


class CandidateEffectPanelTests(unittest.TestCase):
    def _history(self):
        return [
            {"race_id": "r2014", "county_id": "c1", "county": "A", "office": "local_executive", "year": 2014,
             "candidates": [
                 {"name": "DPP A", "party": "DPP", "share_pct": 48, "winner": False},
                 {"name": "KMT A", "party": "KMT", "share_pct": 52, "winner": True},
             ]},
            {"race_id": "r2018", "county_id": "c1", "county": "A", "office": "local_executive", "year": 2018,
             "candidates": [
                 {"name": "DPP A", "party": "DPP", "share_pct": 51, "winner": True},
                 {"name": "KMT B", "party": "KMT", "share_pct": 49, "winner": False},
             ]},
        ]

    def test_panel_preserves_frozen_baseline_scope(self):
        baseline = {"schema_version": 1, "model_version": "pb4", "rows": [{
            "target_year": 2018, "county_id": "c1", "county": "A",
            "baseline_dpp2": .47, "target_dpp2": .51, "information_weight": .9,
            "major_party_coverage": 1.0, "baseline_scope": "county_oof",
        }]}
        panel = build_panel(baseline, self._history())
        self.assertEqual(len(panel["rows"]), 1)
        row = panel["rows"][0]
        self.assertEqual(row["baseline_scope"], "county_oof")
        self.assertEqual(row["repeat_candidate_signal"], 1)
        self.assertEqual(row["prior_race_id"], "r2014")

    def test_non_two_party_matchup_is_excluded(self):
        history = self._history()
        history[1]["candidates"] = [
            {"name": "DPP A", "party": "DPP", "share_pct": 40, "winner": False},
            {"name": "TPP A", "party": "TPP", "share_pct": 60, "winner": True},
        ]
        baseline = {"schema_version": 1, "rows": [{
            "target_year": 2018, "county_id": "c1", "baseline_dpp2": .47,
            "target_dpp2": .51, "information_weight": .5,
            "major_party_coverage": .4, "baseline_scope": "county_oof",
        }]}
        panel = build_panel(baseline, history)
        self.assertEqual(panel["rows"], [])
        self.assertFalse(panel["audit"][0]["included"])


if __name__ == "__main__":
    unittest.main()
