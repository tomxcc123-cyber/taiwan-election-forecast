import unittest

from model.integrated_prior import lagged_turnout_features, replace_major_split


class IntegratedPriorTests(unittest.TestCase):
    def test_lagged_turnout_uses_only_prior_cycles(self):
        history = [
            {"race_id": "r14", "county_id": "c", "office": "local_executive", "year": 2014,
             "turnout_pct": 60.0},
            {"race_id": "r18", "county_id": "c", "office": "local_executive", "year": 2018,
             "turnout_pct": 64.0},
            {"race_id": "r22", "county_id": "c", "office": "local_executive", "year": 2022,
             "turnout_pct": 59.0},
        ]
        target = {"race_id": "r26", "county_id": "c", "office": "local_executive", "year": 2026}
        got = lagged_turnout_features(history, target)
        self.assertAlmostEqual(got["previous_turnout"], 0.59)
        self.assertAlmostEqual(got["turnout_trend"], -0.05)
        self.assertEqual(got["turnout_available"], 1.0)
        self.assertEqual(got["turnout_trend_available"], 1.0)

    def test_missing_early_turnout_is_availability_coded(self):
        history = [
            {"race_id": "r10", "county_id": "c", "office": "local_executive", "year": 2010},
        ]
        target = {"race_id": "r14", "county_id": "c", "office": "local_executive", "year": 2014}
        got = lagged_turnout_features(history, target)
        self.assertEqual(got["previous_turnout"], 0.0)
        self.assertEqual(got["turnout_available"], 0.0)
        self.assertEqual(got["turnout_trend"], 0.0)
        self.assertEqual(got["turnout_trend_available"], 0.0)

    def test_replace_major_split_preserves_nonmajor_mass(self):
        race = {"candidates": [
            {"name": "D", "party": "DPP"},
            {"name": "K", "party": "KMT"},
            {"name": "I", "party": None},
        ]}
        next_center, applied = replace_major_split([0.40, 0.45, 0.15], race, 0.60)
        self.assertTrue(applied)
        self.assertAlmostEqual(next_center[2], 0.15)
        self.assertAlmostEqual(next_center[0], 0.51)
        self.assertAlmostEqual(next_center[1], 0.34)
        self.assertAlmostEqual(sum(next_center), 1.0)

    def test_replace_major_split_requires_unique_pair(self):
        race = {"candidates": [
            {"name": "D", "party": "DPP"},
            {"name": "I", "party": None},
        ]}
        next_center, applied = replace_major_split([0.6, 0.4], race, 0.55)
        self.assertFalse(applied)
        self.assertEqual(next_center, [0.6, 0.4])


if __name__ == "__main__":
    unittest.main()
