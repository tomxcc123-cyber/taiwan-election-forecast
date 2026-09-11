import unittest

import numpy as np

from model.election_environment import (diagnose_cycle,
                                        historical_environment_scale,
                                        widen_logit_sd)


class ElectionEnvironmentTests(unittest.TestCase):
    def test_common_shock_explains_shared_direction_error(self):
        rows = [
            {"target_dpp2": .40, "major_party_coverage": 1.0},
            {"target_dpp2": .45, "major_party_coverage": 1.0},
            {"target_dpp2": .50, "major_party_coverage": 1.0},
        ]
        predicted = np.array([.50, .55, .60])
        diag = diagnose_cycle(predicted, rows)
        self.assertLess(diag["cycle_shock_logit_actual_minus_structural"], 0)
        self.assertGreater(diag["weighted_sse_fraction_explained_by_common_shock"], .8)

    def test_no_common_shock_when_errors_cancel(self):
        rows = [
            {"target_dpp2": .40, "major_party_coverage": 1.0},
            {"target_dpp2": .60, "major_party_coverage": 1.0},
        ]
        predicted = np.array([.50, .50])
        diag = diagnose_cycle(predicted, rows)
        self.assertAlmostEqual(diag["cycle_shock_logit_actual_minus_structural"], 0.0, places=10)
        self.assertAlmostEqual(diag["weighted_sse_fraction_explained_by_common_shock"], 0.0, places=10)

    def test_environment_scale_is_zero_centered_rms(self):
        diags = [
            {"cycle_shock_logit_actual_minus_structural": -.4},
            {"cycle_shock_logit_actual_minus_structural": .2},
        ]
        scale = historical_environment_scale(diags)
        self.assertTrue(scale["mean_zero_by_design"])
        self.assertAlmostEqual(scale["rms_shock_logit"], np.sqrt((.16 + .04)/2))

    def test_uncertainty_combines_in_quadrature(self):
        self.assertAlmostEqual(widen_logit_sd(.3, .4), .5)


if __name__ == "__main__":
    unittest.main()
