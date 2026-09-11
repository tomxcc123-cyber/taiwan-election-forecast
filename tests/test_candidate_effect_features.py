import unittest

from model.candidate_effect_features import build_pair_features


class CandidateEffectFeatureTests(unittest.TestCase):
    def _history(self):
        return [
            {"race_id": "r2014", "county_id": "c1", "office": "local_executive", "year": 2014,
             "candidates": [
                 {"name": "DPP A", "party": "DPP", "share_pct": 48, "winner": False},
                 {"name": "KMT A", "party": "KMT", "share_pct": 52, "winner": True},
             ]},
            {"race_id": "r2018", "county_id": "c1", "office": "local_executive", "year": 2018,
             "candidates": [
                 {"name": "DPP A", "party": "DPP", "share_pct": 51, "winner": True},
                 {"name": "KMT B", "party": "KMT", "share_pct": 49, "winner": False},
             ]},
        ]

    def test_exact_name_repeat_and_previous_winner_are_signed(self):
        history = self._history()
        features = build_pair_features(history[1], history)
        self.assertEqual(features["repeat_candidate_signal"], 1)
        self.assertEqual(features["prior_winner_signal"], 0)
        self.assertGreater(features["previous_candidate_share_signal"], 0)

    def test_verified_incumbency_is_not_inferred_from_previous_winner(self):
        history = self._history()
        features = build_pair_features(history[1], history)
        self.assertEqual(features["verified_incumbency_signal"], 0)
        verified = build_pair_features(history[1], history, verified_incumbent_party="KMT")
        self.assertEqual(verified["verified_incumbency_signal"], -1)

    def test_prior_candidate_effect_requires_explicit_prior_estimate(self):
        history = self._history()
        features = build_pair_features(history[1], history,
                                       prior_candidate_effects={"DPP A": .12})
        self.assertAlmostEqual(features["prior_candidate_residual_signal"], .12)


if __name__ == "__main__":
    unittest.main()
