import unittest

import numpy as np

from model.fragmentation_live import (
    STRONG_NONMAJOR_THRESHOLD,
    apply_live_fragmentation_gate,
    find_triggers,
)


class FragmentationLiveTests(unittest.TestCase):
    def product(self):
        draws = [[500000, 350000, 150000] for _ in range(200)]
        return {
            "counties": [{
                "name": "新竹市",
                "candidates": [
                    {"candidate_id": "k", "name": "林耕仁", "party": "KMT", "mean": 50, "p05": 45, "p95": 55, "probability": .9},
                    {"candidate_id": "d", "name": "沈慧虹", "party": "DPP", "mean": 35, "p05": 30, "p95": 40, "probability": .1},
                    {"candidate_id": "t", "name": "高虹安", "party": "TPP", "mean": 15, "p05": 10, "p95": 20, "probability": 0},
                ],
                "draws": draws,
                "v4_structural": {},
            }],
            "poll_audit": [{"id": "p1", "included": True}],
            "diagnostics": {},
        }

    def feed(self, supports=(25, 32, 43), source="TVBS 民意調查中心"):
        return {"records": [{
            "id": "p1",
            "county": "新竹市",
            "source": source,
            "date": "2026-10-30",
            "sample_n": 1000,
            "candidates": [
                {"name": "林耕仁", "support": supports[0]},
                {"name": "沈慧虹", "support": supports[1]},
                {"name": "高虹安", "support": supports[2]},
            ],
        }]}

    def test_strong_full_field_tvbs_triggers(self):
        triggers = find_triggers(self.product(), self.feed())
        self.assertEqual(len(triggers), 1)
        self.assertGreaterEqual(triggers[0]["nonmajor_decided_share"], STRONG_NONMAJOR_THRESHOLD)

    def test_partial_ballot_does_not_trigger(self):
        feed = self.feed()
        feed["records"][0]["candidates"].pop()
        self.assertEqual(find_triggers(self.product(), feed), [])

    def test_non_tvbs_does_not_trigger(self):
        self.assertEqual(find_triggers(self.product(), self.feed(source="其他機構")), [])

    def test_weak_fragmentation_does_not_trigger(self):
        self.assertEqual(find_triggers(self.product(), self.feed((45, 40, 15))), [])

    def test_gate_recenters_full_vector_and_preserves_valid_draws(self):
        product = self.product()
        result = apply_live_fragmentation_gate(product, self.feed())
        county = result["counties"][0]
        draws = np.asarray(county["draws"], dtype=int)
        self.assertTrue(np.all(draws.sum(axis=1) == 1_000_000))
        means = np.asarray([c["mean"] for c in county["candidates"]]) / 100
        np.testing.assert_allclose(means, np.asarray([.25, .32, .43]), atol=2e-3)
        self.assertEqual(county["candidates"][2]["probability"], 1.0)
        self.assertEqual(result["fragmentation_gate"]["triggered_count"], 1)
        self.assertEqual(result["diagnostics"]["strong_fragmentation_gate_count"], 1)


if __name__ == "__main__":
    unittest.main()
