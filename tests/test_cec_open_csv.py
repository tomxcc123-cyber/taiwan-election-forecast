import unittest
from zipfile import ZipFile
from io import BytesIO
from scripts.import_cec_open_csv import (dequote,numeric,zone_key,rows_from_bytes,
    collect_profile_groups,pick_paths)

class OfficialCECFormats(unittest.TestCase):
    def test_old_excel_csv_quote_prefix(self):
        self.assertEqual(dequote("'10"),'10')
        self.assertEqual(zone_key(["'10","'004","'00","'010","'0002","1"]),
                         ('10','004','00','010','0002','0001'))
        self.assertEqual(numeric("'0007"),7)
        self.assertRaises(ValueError,numeric,'bad')
    def test_2022_geography_and_station_summary(self):
        files={
          'elbase.csv':'09,007,00,000,0000,連江縣\n09,007,00,010,0000,南竿鄉\n09,007,00,010,0001,介壽村\n',
          'elprof.csv':'09,007,00,000,0000,0000,198,2,200,300,0\n09,007,00,010,0001,0001,99,1,100,150,0\n09,007,00,010,0001,0002,99,1,100,150,0\n',
          'elctks.csv':'09,007,00,010,0001,0001,1,90,90.9,*\n'
        }
        raw_zip=BytesIO()
        with ZipFile(raw_zip,'w') as z:
            prefix='votedata/voteData/2022-111年地方公職人員選舉/C1/city/'
            for name,contents in files.items():z.writestr(prefix+name,contents.encode())
        raw_zip.seek(0)
        with ZipFile(raw_zip) as z:
            selected=pick_paths(z)
            self.assertEqual(len(selected),1)
            path=next(iter(selected.values()))
            raw,names,labels,groups,totals=collect_profile_groups(z,2022,path)
            key=('09','007')
            self.assertEqual(names[key],'連江縣')
            self.assertEqual(labels[('09','007','00','010','0000')],'南竿鄉')
            self.assertEqual(len(groups[key]),2)
            self.assertEqual(totals[key]['ballots_cast'],200)
            self.assertEqual(sum(r['ballots_cast'] for _,r in groups[key]),200)
    def test_2014_quoted_csv(self):
        data=b'"\'10","\'004","\'00","\'010","\'0001","1","50","0","50","75","0"\n'
        rows=rows_from_bytes(data)
        self.assertEqual(zone_key(rows[0]),('10','004','00','010','0001','0001'))
        self.assertEqual(numeric(rows[0][9]),75)

if __name__=='__main__':unittest.main()
