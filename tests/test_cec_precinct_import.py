"""Synthetic-only tests; tests parser arithmetic, never fabricates real CEC station data."""
import copy
import unittest
from scripts.import_cec_precincts import parse_precinct_sheet

class FakeSheet:
    def __init__(self,rows):
        self.rows=rows
        self.nrows=len(rows)
    def row_values(self,index):
        return self.rows[index]
    def cell_value(self,i,j):
        return self.rows[i][j]

def sample():
    def row(a='',station='',vals=()):
        return [a,'',station,*list(vals)]
    headers=row('', '', ['1','2','有效票數','無效票數','投票數',
                         '用餘票','票總','選票備註','選舉人數'])
    names=row('', '', ['1\n候選甲\n政黨甲','2\n候選乙\n政黨乙']+['']*7)
    # Two sample booths, all accounting identities must hold.
    x=[60,40,100,2,102,18,120,0,120]
    y=[30,70,100,2,102,18,120,0,120]
    total=[a+b for a,b in zip(x,y)]
    return FakeSheet([row('111年地方選舉'),headers,names,
      row('中正區','',total),row('','0001',x),row('','0002',y)])

class PrecinctSheetTests(unittest.TestCase):
    def test_counts_and_provenance(self):
        v=parse_precinct_sheet(sample())
        self.assertEqual(len(v['precincts']),2)
        self.assertEqual(v['precincts'][0]['candidate_votes'],{'候選甲':60,'候選乙':40})
        self.assertEqual(v['precincts'][0]['valid_votes'],100)
        self.assertEqual(v['precincts'][0]['ballots_cast'],102)
        self.assertEqual(v['precincts'][0]['electorate'],120)
        self.assertAlmostEqual(v['precincts'][0]['turnout_rate'],.85)
        self.assertEqual(v['districts'][0]['precinct_count'],2)
        self.assertEqual(v['districts'][0]['ballots_cast'],204)
    def test_duplicate_station_rejected(self):
        sheet=sample()
        sheet.rows[5][2]='0001'
        with self.assertRaisesRegex(ValueError,'Duplicate precinct'):
            parse_precinct_sheet(sheet)
    def test_invalid_ballot_count_rejected(self):
        sheet=sample()
        sheet.rows[4][6]=3
        with self.assertRaisesRegex(ValueError,'Vote conservation'):
            parse_precinct_sheet(sheet)
    def test_district_mismatch_rejected(self):
        sheet=sample()
        sheet.rows[3][10]+=1
        with self.assertRaisesRegex(ValueError,'District sum'):
            parse_precinct_sheet(sheet)
    def test_station_inventory_discrepancy_retained(self):
        sheet=sample()
        sheet.rows[4][10]=1  # The extra issue-balance term; keep audit flag.
        sheet.rows[3][10]=1  # Station and district both contain the audited discrepancy.
        self.assertEqual(parse_precinct_sheet(sheet)['precincts'][0]['inventory_delta'],1)
    def test_non_int_rejected(self):
        sheet=sample()
        sheet.rows[4][3]='60.5'
        with self.assertRaises(ValueError):
            parse_precinct_sheet(sheet)

if __name__=='__main__':
    unittest.main()
