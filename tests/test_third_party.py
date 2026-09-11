import unittest

import numpy as np

from model.third_party import compose_bloc_shares, fit, metrics, predict


class ThirdPartyTests(unittest.TestCase):
    def rows(self):
        return [
            {"target_year": 2014, "target_nonmajor_share": .05, "information_weight": 1,
             "previous_nonmajor_share": .04, "council_independent_share": .10,
             "town_independent_share": .10, "town_available": 1,
             "faction_propensity": .08, "log_nonmajor_candidate_count": np.log1p(1)},
            {"target_year": 2014, "target_nonmajor_share": .35, "information_weight": 1,
             "previous_nonmajor_share": .30, "council_independent_share": .40,
             "town_independent_share": .45, "town_available": 1,
             "faction_propensity": .36, "log_nonmajor_candidate_count": np.log1p(3)},
            {"target_year": 2014, "target_nonmajor_share": .15, "information_weight": 1,
             "previous_nonmajor_share": .12, "council_independent_share": .22,
             "town_independent_share": 0, "town_available": 0,
             "faction_propensity": .13, "log_nonmajor_candidate_count": np.log1p(2)},
        ]

    def test_predictions_are_valid_shares(self):
        rows = self.rows()
        model = fit(rows, alpha=3)
        p = predict(model, rows)
        self.assertTrue(np.all((p > 0) & (p < 1)))

    def test_higher_prior_nonmajor_can_raise_prediction(self):
        rows = self.rows()
        model = fit(rows, alpha=1)
        low = dict(rows[0]); high = dict(rows[0])
        low["previous_nonmajor_share"] = .02
        high["previous_nonmajor_share"] = .50
        self.assertGreater(float(predict(model, [high])[0]), float(predict(model, [low])[0]))

    def test_composition_conserves_mass(self):
        value = compose_bloc_shares(.55, .20)
        self.assertAlmostEqual(sum(value.values()), 1.0, places=12)
        self.assertAlmostEqual(value["DPP"], .44, places=12)
        self.assertAlmostEqual(value["KMT"], .36, places=12)
        self.assertAlmostEqual(value["NONMAJOR"], .20, places=12)

    def test_metrics_report_strong_nonmajor_subset(self):
        rows = self.rows()
        result = metrics([.06, .30, .14], rows)
        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["strong_nonmajor_rows"], 1)
        self.assertTrue(np.isfinite(result["mae_pp"]))


if __name__ == "__main__":
    unittest.main()
