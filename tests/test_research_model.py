import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from scripts.research_model import evaluate, historical_prediction, prepare


class HistoricalTests(unittest.TestCase):
    def test_no_future_leakage(self):
        h = {str(y): {'shares': {'KMT': x, 'DPP': 100-x}}
             for y, x in ((2014, 40), (2018, 50), (2022, 70))}
        before = historical_prediction(h, 2022, 'ensemble')
        h['2022']['shares'] = {'KMT': 0, 'DPP': 100}
        self.assertEqual(before, historical_prediction(h, 2022, 'ensemble'))
        self.assertAlmostEqual(before['KMT'], 140/3)

    def test_last_baseline(self):
        h = {'2014': {'shares': {'KMT': 41, 'DPP': 59}},
             '2018': {'shares': {'KMT': 51, 'DPP': 49}}}
        self.assertEqual(historical_prediction(h, 2018, 'last')['KMT'], 41)
        with self.assertRaises(ValueError): historical_prediction(h, 2010, 'last')

    def test_real_input(self):
        root = Path(__file__).resolve().parents[1]
        data = prepare(root, datetime(2026, 9, 7, tzinfo=timezone.utc))
        self.assertEqual(len(data['counties']), 22)
        self.assertEqual(len(data['validation']), 4)
        for row in data['validation']:
            self.assertEqual(row['n'], 44)
            self.assertLess(max(row['training_years']), row['year'])
            self.assertGreaterEqual(row['rmse'], row['mae'])
        # The June priors remain traceable rather than silently relabeled as newly trained means.
        self.assertEqual(data['baseline_date'], '2026-06-27')


if __name__ == '__main__': unittest.main()
