import unittest
from scripts.update_market_snapshots import build_snapshot, normalize_event

SPEC = {'county': '台北市', 'slug': 'taipei-mayor-election-winner-20260813125857100'}
STAMP = '2026-10-28T08:00:00+00:00'

def valid_event():
    return [{
        'slug': SPEC['slug'], 'id': '1234', 'title': 'Taipei Mayor Election Winner',
        'description': 'Taiwanese local elections are scheduled to be held on November 28, 2026.',
        'active': True, 'closed': False, 'volume': '62000', 'liquidity': '18000',
        'updatedAt': STAMP,
        'markets': [
            {'id': '100', 'groupItemTitle': 'Chiang Wan-an', 'outcomes': '["Yes","No"]',
             'outcomePrices': '["0.63","0.37"]', 'active': True, 'closed': False,
             'volumeNum': 50000, 'liquidityNum': 14000, 'bestBid': 0.62, 'bestAsk': 0.64},
            {'id': '101', 'groupItemTitle': 'Puma Shen', 'outcomes': '["Yes","No"]',
             'outcomePrices': '["0.37","0.63"]', 'active': True, 'closed': False,
             'volumeNum': 12000, 'liquidityNum': 4000, 'bestBid': 0.36, 'bestAsk': 0.38},
        ],
    }]

class MarketSnapshotsTest(unittest.TestCase):
    def test_values_are_yes_contract_prices_and_not_renormalized(self):
        record = normalize_event(valid_event(), SPEC, STAMP)
        self.assertEqual(record['county'], '台北市')
        self.assertEqual([r['probability'] for r in record['outcomes']], [0.63, 0.37])
        self.assertAlmostEqual(record['outcomes'][0]['spread'], 0.02)
        self.assertFalse(record['stale'])

    def test_inconsistent_contract_rules_fail_closed(self):
        event = valid_event()
        event[0]['description'] = '2028 US presidential race'
        with self.assertRaises(ValueError):
            normalize_event(event, SPEC, STAMP)

    def test_invalid_prices_are_not_published(self):
        event = valid_event()
        for row in event[0]['markets']:
            row['outcomePrices'] = '["1.7","-0.7"]'
        with self.assertRaises(ValueError):
            normalize_event(event, SPEC, STAMP)

    def test_partial_source_failure_retains_stale_and_no_fake_history(self):
        cfg = {'schema_version': 1, 'events': [SPEC, {'county': '台中市', 'slug': 'taichung-mayor-election-winner-20260813125857400'}]}
        first = build_snapshot({'schema_version': 1, 'events': [SPEC]}, {}, lambda _: valid_event(), STAMP)
        later = build_snapshot(cfg, first, lambda _: (_ for _ in ()).throw(OSError('temporary failure')), '2026-10-28T14:00:00+00:00')
        self.assertEqual(later['status'], 'degraded')
        self.assertEqual(len(later['events']), 1)
        self.assertTrue(later['events'][0]['stale'])
        self.assertEqual(len(later['history']), len(first['history']))
        self.assertEqual(len(later['errors']), 2)

    def test_snapshot_history_preserves_unmodified_quotes(self):
        config = {'schema_version': 1, 'events': [SPEC]}
        first = build_snapshot(config, {}, lambda _: valid_event(), STAMP)
        second = build_snapshot(config, first, lambda _: valid_event(), '2026-10-28T14:00:00+00:00')
        self.assertEqual(len(second['history']), 4)
        self.assertTrue(second['research_only'])
        self.assertFalse(second['used_in_forecast'])

if __name__ == '__main__':
    unittest.main()
