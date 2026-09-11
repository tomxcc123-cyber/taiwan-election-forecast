import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from model.v4_product import MODEL_ID, build_product


ROOT = Path(__file__).resolve().parents[1]


class V4ProductionProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        feed = json.loads((ROOT / 'data/polls.json').read_text(encoding='utf-8'))
        cls.product = build_product(ROOT, datetime(2026, 9, 11, 15, 0, tzinfo=timezone.utc), feed)

    def test_v4_is_the_production_structural_center(self):
        product = self.product
        self.assertEqual(product['model_id'], MODEL_ID)
        self.assertEqual(product['release_status'], 'public_beta')
        self.assertTrue(product['release']['public_beta'])
        self.assertFalse(product['release']['stable'])
        self.assertEqual(product['structural_model']['id'], MODEL_ID)
        self.assertEqual(sum(product['diagnostics']['structural_mode_counts'].values()), 22)

    def test_public_candidate_contract_is_complete(self):
        product = self.product
        self.assertEqual(len(product['counties']), 22)
        self.assertEqual(sum(len(r['candidates']) for r in product['counties']), 81)
        self.assertEqual(product['simulations'], 2000)
        for race in product['counties']:
            self.assertEqual(len(race['draws']), 2000)
            self.assertIn(race['v4_structural']['mode'], {
                'v4_compositional', 'fallback_direct_fundamentals'
            })
            self.assertAlmostEqual(sum(c['mean'] for c in race['candidates']), 100.0, places=6)
            self.assertAlmostEqual(sum(c['probability'] for c in race['candidates']), 1.0, places=6)

    def test_bridge_is_explicit_not_silent(self):
        structural = self.product['structural_model']
        self.assertTrue(self.product['release']['organization_bridge'])
        self.assertEqual(structural['current_features']['organization_bridge']['organization_feature_vintage'], 2018)
        self.assertIn('Public Beta bridge only', structural['current_features']['organization_bridge']['policy'])


if __name__ == '__main__':
    unittest.main()
