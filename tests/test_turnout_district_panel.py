"""Historical CEC town panel tests; source fixtures never masquerade as real votes."""
import unittest
from scripts.build_turnout_district_panel import analyze_county_record,name_norm

def record(year=2022):
    data=[
      ('0001','甲區',50,55,80),('0002','甲區',40,45,65),('0003','乙區',35,37,55)
    ]
    precincts=[]
    for number,label,valid,cast,eligible in data:
        idx='010' if label=='甲區' else '020'
        precincts.append({'geo_codes':['63','000','00',idx,number,number],
         'district_name':label,'precinct_number':number,
         'valid_votes':valid,'invalid_votes':cast-valid,
         'ballots_cast':cast,'electorate':eligible})
    totals={f:sum(x[f] for x in precincts) for f in
            ('valid_votes','invalid_votes','ballots_cast','electorate')}
    source={'schema_version':1,'year':year,'county':'台北市','precincts':precincts,
     'precinct_count':len(precincts),'totals':totals}
    entry={'year':year,'county':'台北市','precinct_count':len(precincts),
      'totals':totals}
    return source,entry

class TownPanelTests(unittest.TestCase):
    def test_rollup(self):
        r,e=record()
        districts,sums=analyze_county_record(r,e)
        self.assertEqual(len(districts),2)
        a=districts['63/000/00/010']
        self.assertEqual(a['name'],'甲區')
        self.assertEqual(a['stations'],2)
        self.assertEqual(a['electorate'],145)
        self.assertEqual(a['ballots_cast'],100)
        self.assertEqual(sums['ballots_cast'],137)
    def test_missing_label_fails(self):
        r,e=record();r['precincts'][0]['district_name']=None
        with self.assertRaisesRegex(ValueError,'label missing'):
            analyze_county_record(r,e)
    def test_duplicate_station_fails(self):
        r,e=record();r['precincts'][1]['geo_codes']=r['precincts'][0]['geo_codes']
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            analyze_county_record(r,e)
    def test_changed_labels_fail(self):
        r,e=record();r['precincts'][1]['district_name']='乙區'
        with self.assertRaisesRegex(ValueError,'conflicting names'):
            analyze_county_record(r,e)
    def test_count_totals_fail(self):
        r,e=record();e['totals']['ballots_cast']+=1
        with self.assertRaisesRegex(ValueError,'totals mismatch'):
            analyze_county_record(r,e)
    def test_valid_invalid_fail(self):
        r,e=record();r['precincts'][0]['invalid_votes']=0
        with self.assertRaisesRegex(ValueError,'conservation'):
            analyze_county_record(r,e)
    def test_normalization(self):
        self.assertEqual(name_norm(' 臺北　'),'台北')

if __name__=='__main__':unittest.main()
