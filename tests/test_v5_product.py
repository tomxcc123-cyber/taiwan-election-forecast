import unittest

import numpy as np

from model.v5_product import MODEL_ID, VERSION, _compose_unified


class V5ProductTests(unittest.TestCase):
    def test_version_is_public_beta_v5(self):
        self.assertEqual(MODEL_ID, "HB-TLEF-v5.0-public-beta.1")
        self.assertEqual(VERSION, "2026.09-HB-TLEF-v5.0-public-beta.1")

    def test_unified_composition_preserves_nonmajor_mass(self):
        race = {
            "candidates": [
                {"name": "D", "party": "DPP"},
                {"name": "K", "party": "KMT"},
                {"name": "I1", "party": None},
                {"name": "I2", "party": "TPP"},
            ]
        }
        legacy = np.array([.35, .40, .20, .05])
        out, mode = _compose_unified(race, legacy, .30, .55)
        self.assertEqual(mode, "integrated_r4_candidate_t3")
        self.assertAlmostEqual(float(out.sum()), 1.0, places=12)
        self.assertAlmostEqual(float(out[0] + out[1]), .70, places=12)
        self.assertAlmostEqual(float(out[2] + out[3]), .30, places=12)
        self.assertAlmostEqual(float(out[0] / (out[0] + out[1])), .55, places=12)
        self.assertAlmostEqual(float(out[2] / out[3]), 4.0, places=12)

    def test_non_unique_major_pair_uses_full_legacy_vector(self):
        race = {
            "candidates": [
                {"name": "K", "party": "KMT"},
                {"name": "I", "party": None},
            ]
        }
        legacy = np.array([.72, .28])
        out, mode = _compose_unified(race, legacy, .40, .30)
        self.assertEqual(mode, "legacy_full_missing_unique_major_pair")
        np.testing.assert_allclose(out, legacy)


if __name__ == "__main__":
    unittest.main()
