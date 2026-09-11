import unittest

from model.baseline_data import (FutureDataLeakage, assert_available_before,
                                 information_weight, major_party_coverage,
                                 two_party_dpp_share)
from model.partisan_baseline import fit, predict


def _race(kmt, dpp, ind=0):
    valid = kmt+dpp+ind
    return [
        {"party_std": "KMT", "votes": kmt, "valid_votes": valid},
        {"party_std": "DPP", "votes": dpp, "valid_votes": valid},
        {"party_std": "IND", "votes": ind, "valid_votes": valid},
    ]


class PartisanBaselineTests(unittest.TestCase):
    def test_two_party_share_ignores_independent_votes(self):
        rows = _race(40, 50, 10)
        self.assertAlmostEqual(two_party_dpp_share(rows), 50/90)
        self.assertAlmostEqual(major_party_coverage(rows), .9)

    def test_information_weight_downweights_independent_dominance(self):
        normal = information_weight(_race(48, 49, 3))
        factional = information_weight(_race(11, 31, 58))
        self.assertGreater(normal, factional)

    def test_temporal_leakage_gate_rejects_same_day_information(self):
        with self.assertRaises(FutureDataLeakage):
            assert_available_before("2022_council", "2022-11-26", "2022-11-26")

    def test_weighted_ridge_predicts_valid_two_party_shares(self):
        features = ["previous_local_dpp2", "presidential_relative_lean"]
        rows = [
            {"target_year": 2014, "county_id": "a", "target_dpp2": .42,
             "information_weight": .9, "previous_local_dpp2": .40, "presidential_relative_lean": -.05},
            {"target_year": 2014, "county_id": "b", "target_dpp2": .58,
             "information_weight": .9, "previous_local_dpp2": .56, "presidential_relative_lean": .05},
            {"target_year": 2018, "county_id": "a", "target_dpp2": .44,
             "information_weight": .9, "previous_local_dpp2": .42, "presidential_relative_lean": -.03},
            {"target_year": 2018, "county_id": "b", "target_dpp2": .56,
             "information_weight": .9, "previous_local_dpp2": .58, "presidential_relative_lean": .03},
        ]
        model = fit(rows, features=features, alpha=1.0)
        pred = predict(model, rows)
        self.assertEqual(len(pred), 4)
        self.assertTrue(all(0 < p < 1 for p in pred))


if __name__ == "__main__":
    unittest.main()
