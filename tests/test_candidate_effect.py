import unittest

from model.candidate_effect import (adjust_baseline, fit, residual_target_logit,
                                    select_alpha)
from model.candidate_effect_pipeline import run


class CandidateEffectTests(unittest.TestCase):
    def test_zero_candidate_asymmetry_leaves_baseline_near_unchanged(self):
        rows = [
            {"target_year": 2018, "county_id": "a", "baseline_dpp2": .45, "target_dpp2": .45,
             "information_weight": 1.0, "repeat_candidate_signal": 0,
             "prior_winner_signal": 0, "prior_candidate_residual_signal": 0,
             "verified_incumbency_signal": 0},
            {"target_year": 2018, "county_id": "b", "baseline_dpp2": .55, "target_dpp2": .55,
             "information_weight": 1.0, "repeat_candidate_signal": 0,
             "prior_winner_signal": 0, "prior_candidate_residual_signal": 0,
             "verified_incumbency_signal": 0},
        ]
        model = fit(rows, alpha=10.0)
        pred = adjust_baseline(model, rows)
        self.assertAlmostEqual(float(pred[0]), .45, places=10)
        self.assertAlmostEqual(float(pred[1]), .55, places=10)

    def test_positive_dpp_candidate_signal_can_raise_dpp_share(self):
        rows = [
            {"target_year": 2018, "county_id": "a", "baseline_dpp2": .50, "target_dpp2": .56,
             "information_weight": 1.0, "repeat_candidate_signal": 1,
             "prior_winner_signal": 1, "prior_candidate_residual_signal": .15,
             "verified_incumbency_signal": 1},
            {"target_year": 2018, "county_id": "b", "baseline_dpp2": .50, "target_dpp2": .44,
             "information_weight": 1.0, "repeat_candidate_signal": -1,
             "prior_winner_signal": -1, "prior_candidate_residual_signal": -.15,
             "verified_incumbency_signal": -1},
        ]
        model = fit(rows, alpha=.3)
        pred = adjust_baseline(model, rows)
        self.assertGreater(float(pred[0]), .50)
        self.assertLess(float(pred[1]), .50)

    def test_target_is_residual_to_frozen_baseline(self):
        row = {"baseline_dpp2": .50, "target_dpp2": .60}
        self.assertGreater(residual_target_logit(row), 0)

    def test_alpha_selection_uses_training_rows_only(self):
        rows = []
        for i, signal in enumerate([-1, -0.5, 0.5, 1]):
            rows.append({
                "target_year": 2018, "county_id": f"c{i}", "baseline_dpp2": .50,
                "target_dpp2": .50 + .04*signal, "information_weight": 1.0,
                "repeat_candidate_signal": signal, "prior_winner_signal": 0,
                "prior_candidate_residual_signal": 0, "verified_incumbency_signal": 0,
            })
        result = select_alpha(rows, grid=(1.0, 10.0))
        self.assertIn(result["selected_alpha"], (1.0, 10.0))
        self.assertEqual(len(result["candidates"]), 2)

    def test_pipeline_rejects_in_sample_structural_training_labels(self):
        rows = []
        for i in range(4):
            rows.append({
                "target_year": 2018, "county_id": f"train{i}",
                "baseline_scope": "in_sample", "baseline_dpp2": .50,
                "target_dpp2": .50, "information_weight": 1.0,
                "repeat_candidate_signal": 0, "prior_winner_signal": 0,
                "prior_candidate_residual_signal": 0, "verified_incumbency_signal": 0,
            })
        rows.append({
            "target_year": 2022, "county_id": "test", "baseline_scope": "time_holdout",
            "baseline_dpp2": .50, "target_dpp2": .50, "information_weight": 1.0,
            "repeat_candidate_signal": 0, "prior_winner_signal": 0,
            "prior_candidate_residual_signal": 0, "verified_incumbency_signal": 0,
        })
        with self.assertRaises(ValueError):
            run({"schema_version": 1, "rows": rows}, alpha_grid=(10.0,))


if __name__ == "__main__":
    unittest.main()
