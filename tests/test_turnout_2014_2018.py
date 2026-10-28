import unittest
from scripts.build_turnout_2014_2018 import admin_names,audited_town_rollup

def source_elbase():
    return (
    "'63,'000,'00,'000,'0000,臺北市\n"
    "'63,'000,'00,'120,'0000,北投區\n"
    "'63,'000,'00,'120,'0001,建民里\n"
    "'63,'000,'01,'120,'0000,臺北市第01選區\n"
    "'63,'000,'00,'030,'0000,大安區\n").encode('utf8')

def fixture():
    rows=[]
    for number,station in [('0001',70),('0002',80)]:
        rows.append({'geo_codes':['63','000','01','120','0001',number],
            'district_name':None,
            'electorate':100,'ballots_cast':station,
            'valid_votes':station-1,'invalid_votes':1})
    totals={k:sum(x[k] for x in rows) for k in
      ('electorate','ballots_cast','valid_votes','invalid_votes')}
    return ({'year':2014,'county':'台北市','precincts':rows,
          'precinct_count':2,'totals':totals},
          {'year':2014,'county':'台北市','precinct_count':2,'totals':totals})

class Original2014CECTests(unittest.TestCase):
    def test_only_same_year_admin_area_names(self):
        names,amb=admin_names(source_elbase())
        self.assertEqual(amb,0)
        self.assertEqual(names[('63','000','120')],'北投區')
        self.assertNotIn(('63','000','000'),names)
    def test_original_2014_election_code_differs_from_elbase(self):
        original,index=fixture()
        names,_=admin_names(source_elbase())
        towns,missing=audited_town_rollup(original,index,names)
        self.assertEqual(missing,set())
        self.assertEqual(len(towns),1)
        self.assertEqual(towns[('63','000','120')]['name'],'北投區')
        self.assertEqual(towns[('63','000','120')]['ballots_cast'],150)
        self.assertEqual(towns[('63','000','120')]['stations'],2)
    def test_no_backfill_without_original_name(self):
        original,index=fixture()
        towns,missing=audited_town_rollup(original,index,{})
        self.assertEqual(towns,{})
        self.assertEqual(missing,{('63','000','120')})
    def test_wrong_total_rejected(self):
        original,index=fixture()
        index['totals']['ballots_cast']+=1
        with self.assertRaisesRegex(ValueError,'county totals'):
            audited_town_rollup(original,index,admin_names(source_elbase())[0])
    def test_broken_precinct_rejected(self):
        original,index=fixture()
        original['precincts'][0]['invalid_votes']=2
        with self.assertRaisesRegex(ValueError,'conservation'):
            audited_town_rollup(original,index,admin_names(source_elbase())[0])
    def test_duplicate_precinct_rejected(self):
        original,index=fixture()
        original['precincts'][1]['geo_codes']=original['precincts'][0]['geo_codes']
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            audited_town_rollup(original,index,admin_names(source_elbase())[0])
    def test_ambiguous_names_refused(self):
        raw=source_elbase()+b"'63,'000,'00,'120,'0000,wrong\n"
        names,ambiguity=admin_names(raw)
        self.assertEqual(ambiguity,1)
        self.assertNotIn(('63','000','120'),names)

if __name__=='__main__':unittest.main()
