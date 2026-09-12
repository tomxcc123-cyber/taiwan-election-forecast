import copy
import unittest

import numpy as np

from model.fragmentation_live import (
    MAX_TRIGGER_AGE_DAYS,
    STRONG_NONMAJOR_THRESHOLD,
    apply_live_fragmentation_gate,
    find_triggers,
)


class FragmentationLiveTests(unittest.TestCase):
    def product(self):
        draws = [[500000, 350000, 150000] for _ in range(200)]
        return {
            "generated_at": "2026-11-20T12:00:00+00:00",
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
            "release": {},
        }

    def feed(self, supports=(25, 32, 43), source="TVBS 民意調查中心", date="2026-10-30"):
        return {"records": [{
            "id": "p1",
            "county": "新竹市",
            "source": source,
            "date": date,
            "sample_n": 1000,
            "candidates": [
                {"name": "林耕仁", "support": supports[0]},
                {"name": "沈慧虹", "support": supports[1]},
                {"name": "高虹安", "support": supports[2]},
            ],
        }]}

    def test_strong_full_field_tvbs_is_detected_for_shadow(self):
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

    def test_stale_fragmentation_poll_does_not_enter_shadow_gate(self):
        self.assertEqual(MAX_TRIGGER_AGE_DAYS, 60)
        self.assertEqual(find_triggers(self.product(), self.feed(date="2026-08-01")), [])

    def test_shadow_gate_never_mutates_public_forecast(self):
        product = self.product()
        before = copy.deepcopy(product["counties"])
        result = apply_live_fragmentation_gate(product, self.feed())
        self.assertEqual(result["counties"], before)
        self.assertEqual(result["fragmentation_gate"]["status"], "shadow_only")
        self.assertEqual(result["fragmentation_gate"]["triggered_count"], 0)
        self.assertEqual(result["fragmentation_gate"]["shadow_trigger_count"], 1)
        shadow = result["fragmentation_gate"]["shadow_triggers"][0]
        self.assertFalse(shadow["public_forecast_mutated"])
        self.assertGreater(shadow["counterfactual_center_total_variation"], 0)
        self.assertEqual(result["diagnostics"]["strong_fragmentation_gate_count"], 0)
        self.assertEqual(result["diagnostics"]["strong_fragmentation_shadow_count"], 1)
        self.assertFalse(result["release"]["fragmentation_gate_live"])
        self.assertTrue(result["release"]["fragmentation_gate_shadow_only"])


if __name__ == "__main__":
    unittest.main()
