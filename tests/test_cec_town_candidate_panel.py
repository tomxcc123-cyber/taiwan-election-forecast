import unittest
from scripts.build_cec_candidate_turnout_panel import parse_station_votes

def geo(n):return ('63','000','00','010','0001',n)
def data():
    keys={geo('0001'),geo('0002')}
    valid={geo('0001'):100,geo('0002'):80}
    candidates=[{'ballot_number':1,'name':'甲','votes':95,'candidate_id':'a','legacy_bloc':'KMT'},
        {'ballot_number':2,'name':'乙','votes':85,'candidate_id':'b','legacy_bloc':'DPP'}]
    raw=('63,000,00,010,0001,0001,1,60,60.00, \n'
         '63,000,00,010,0001,0001,2,40,40.00, \n'
         '63,000,00,010,0001,0002,1,35,43.75, \n'
         '63,000,00,010,0001,0002,2,45,56.25, \n'
         # subtotal is ignored, never mixed with station rows
         '63,000,00,010,0000,0000,1,95,52.78, \n').encode()
    return raw,keys,valid,candidates

class CECTownCandidateTests(unittest.TestCase):
    def test_exact_station_and_candidate_conservation(self):
        raw,keys,valid,candidates=data()
        rows,ballots=parse_station_votes(raw,keys,valid,candidates)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[geo('0001')][1],60)
        self.assertEqual(rows[geo('0002')][2],45)
        self.assertEqual(ballots[1]['votes'],95)
    def test_station_valid_votes_reject(self):
        raw,keys,valid,candidates=data()
        valid[geo('0001')]=101
        with self.assertRaisesRegex(ValueError,'valid-vote conservation'):
            parse_station_votes(raw,keys,valid,candidates)
    def test_candidate_total_reject(self):
        raw,keys,valid,candidates=data()
        candidates[0]['votes']+=1
        with self.assertRaisesRegex(ValueError,'Official candidate total'):
            parse_station_votes(raw,keys,valid,candidates)
    def test_duplicate_reject(self):
        raw,keys,valid,candidates=data()
        append=b'63,000,00,010,0001,0001,1,60,60.00, \n'
        with self.assertRaisesRegex(ValueError,'Duplicate candidate'):
            parse_station_votes(raw+append,keys,valid,candidates)
    def test_missing_station_reject(self):
        raw,keys,valid,candidates=data()
        raw=raw.replace(b'63,000,00,010,0001,0002,1,35,43.75, \n',b'')
        with self.assertRaisesRegex(ValueError,'valid-vote conservation'):
            parse_station_votes(raw,keys,valid,candidates)
    def test_ballot_order_reject(self):
        raw,keys,valid,candidates=data()
        candidates[1]['ballot_number']=3
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            parse_station_votes(raw,keys,valid,candidates)
    def test_unknown_ballot_reject(self):
        raw,keys,valid,candidates=data()
        raw=raw.replace(b',0001,0002,2,45,',b',0001,0002,3,45,')
        with self.assertRaisesRegex(ValueError,'Unknown CEC candidate'):
            parse_station_votes(raw,keys,valid,candidates)

if __name__=='__main__':unittest.main()
