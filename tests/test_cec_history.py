import copy
import json
from pathlib import Path
import unittest

from model.data import audit_dataset, eligible_cec_transitions, load_dataset
from model.fundamentals import features, fit, utilities
from scripts.import_cec_history import check_counts, integer, parse_sheet

ROOT = Path(__file__).resolve().parents[1]


class FakeSheet:
    def __init__(self, rows):
        self.rows = rows
        self.nrows = len(rows)

    def row_values(self, i):
        return self.rows[i]

    def cell_value(self, i, j):
        return self.rows[i][j]


class CECDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_dataset(ROOT/'data/candidate-history-cec.json')
        cls.history = cls.data['races']

    def test_full_coverage_and_exact_mass(self):
        audit = audit_dataset(self.data)
        self.assertEqual((audit['race_count'], audit['candidate_count'], audit['research_eligible_count']), (66, 271, 66))
        for year in [2014, 2018, 2022]:
            rows = [r for r in self.history if r['year'] == year]
            self.assertEqual(len({r['county'] for r in rows}), 22)
            for r in rows:
                self.assertEqual(sum(c['votes'] for c in r['candidates']), r['valid_votes'])
                self.assertEqual(r['valid_votes']+r['invalid_votes'], r['ballots_cast'])
                for c in r['candidates']:
                    self.assertAlmostEqual(c['share_pct'], c['votes']/r['valid_votes']*100)
                self.assertIsNone(r['available_at'])
                self.assertFalse(r['source_verified'])

    def test_chiayi_delayed_election(self):
        r = next(r for r in self.history if r['year'] == 2022 and r['county'] == '嘉義市')
        self.assertEqual(r['election_date'], '2022-12-18')
        self.assertEqual(r['valid_votes'], 93813)
        self.assertEqual(next(c for c in r['candidates'] if c['winner'])['votes'], 59874)

    def test_precinct_aggregation_does_not_double_count_subtotals(self):
        rows = [['title'], ['', '', '', '', '', '有效票數'], ['', '', '', '1\n甲\n無', '2\n乙\n無'],
                ['區', '', '', 30, 20, 50, 2, 52, 0, 52, 48, 100],
                ['', '里', '1', 10, 10, 20, 1, 21, 0, 21, 29, 50],
                ['', '里', '2', 20, 10, 30, 1, 31, 0, 31, 19, 50]]
        names, _, total, checks = parse_sheet(FakeSheet(rows))
        self.assertEqual(names, ['甲', '乙'])
        self.assertEqual(total[:2], [30, 20])
        self.assertEqual(checks['precincts'], 2)
        bad = copy.deepcopy(rows);bad[-1][3] += 1
        with self.assertRaises(ValueError):
            parse_sheet(FakeSheet(bad))
        bad = copy.deepcopy(rows);bad[-1][2] = '1'
        with self.assertRaises(ValueError):
            parse_sheet(FakeSheet(bad))

    def test_inventory_difference_is_not_vote_correction(self):
        self.assertEqual(check_counts([30,20,50,2,52,0,52,49,100], 2), 1)
        with self.assertRaises(ValueError):
            check_counts([31,20,50,2,52,0,52,48,100], 2)
        self.assertEqual(integer('1,234'), 1234)
        for value in ['NaN', -1, 1.5]:
            with self.assertRaises(ValueError):
                integer(value)
        warning = next(r for r in self.history if r['county']=='台北市' and r['year']==2018)['source']['checks']['inventory_warnings']
        self.assertEqual(len(warning), 168)

    def test_independents_not_reassigned_to_supported_parties(self):
        r = next(r for r in self.history if r['county']=='台北市' and r['year']==2022)
        c = next(c for c in r['candidates'] if c['name']=='黃珊珊')
        self.assertIsNone(c['party'])
        self.assertEqual(len(r['candidates']), 12)

    def test_names_repaired_with_provenance(self):
        repairs = [c['name_repair'] for r in self.history for c in r['candidates'] if c.get('name_repair')]
        self.assertEqual(len(repairs), 4)
        self.assertEqual({r['canonical'] for r in repairs}, {'游錫堃','傅崐萁','黄師鵬','江聰淵'})
        self.assertTrue(all(r['source_url'].startswith('https://') for r in repairs))

    def test_both_ends_audited_and_no_eight_year_fallback(self):
        eligible = eligible_cec_transitions(self.history)
        self.assertEqual(len(eligible), 44)
        h = copy.deepcopy(self.history)
        next(r for r in h if r['year']==2014 and r['county']=='台北市')['counts_verified'] = False
        self.assertEqual(len(eligible_cec_transitions(h)), 43)
        h = [r for r in self.history if r['year'] != 2018]
        self.assertEqual(eligible_cec_transitions(h), [])

    def test_test_outcomes_cannot_change_features_or_training(self):
        import numpy as np
        train = [r for r in eligible_cec_transitions(self.history) if r['year']==2018]
        target = next(r for r in self.history if r['year']==2022)
        altered = copy.deepcopy(self.history)
        for r in altered:
            if r['year']==2022:
                for c in r['candidates']:
                    c['share_pct']=100/len(r['candidates']);c['winner']=False
        altered_target = next(r for r in altered if r['race_id']==target['race_id'])
        np.testing.assert_array_equal(features(target,self.history), features(altered_target,altered))
        self.assertEqual(fit(train,self.history), fit(train,altered))
        with self.assertRaises(ValueError):
            utilities(fit(train,self.history), train[0], self.history)

    def test_post_election_surveys_stay_out_of_poll_likelihood(self):
        surveys = json.loads((ROOT/'data/survey-source-audit.json').read_text(encoding='utf-8'))
        self.assertFalse(surveys['microdata_published'])
        self.assertEqual(len(surveys['datasets']), 3)
        self.assertTrue(all(not d['included_in_forecast'] for d in surveys['datasets']))


if __name__ == '__main__':
    unittest.main()
