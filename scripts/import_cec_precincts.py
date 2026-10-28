"""Lossless precinct-level conversion of existing user-supplied CEC result workbooks.

The established importer already visits precinct rows but originally discarded
their detailed votes. This deliberately preserves every row in year/county
files, validates rollups against the published audited county history, and
never silently treats missing original archives as available data.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

try:
    from scripts.import_cec_history import ARCHIVES, members, check_counts, integer
except ImportError:
    from import_cec_history import ARCHIVES, members, check_counts, integer

ROOT = Path(__file__).resolve().parents[1]


def normalize(s):
    return str(s or '').strip().replace('臺', '台')


def parse_precinct_sheet(sheet):
    """Return precise booth records and district subtotals, no estimates."""
    headers = sheet.row_values(1)
    end = next((i for i, item in enumerate(headers) if '有效票數' in str(item)), None)
    if end is None or end < 5:
        raise ValueError('Unknown CEC precinct column layout')
    names = []
    for j in range(3, end):
        pieces = str(sheet.cell_value(2, j)).split('\n')
        if len(pieces) < 3 or integer(pieces[0]) != len(names)+1:
            raise ValueError('Invalid candidate header at column '+str(j))
        names.append(normalize(pieces[1]))
    n = len(names)
    districts = []
    precincts = []
    expected = None
    district_totals = [0] * (n+7)
    district = None
    seen = set()

    def finish_district():
        if expected is not None:
            if expected != district_totals:
                raise ValueError('District sum disagrees with station rows: '+str(district))
            districts.append({'district':district,
                              'precinct_count':len([x for x in precincts if x['district']==district]),
                              'candidate_votes':dict(zip(names,expected[:n])),
                              'valid_votes':expected[n],
                              'invalid_votes':expected[n+1],
                              'ballots_cast':expected[n+2],
                              'electorate':expected[n+6]})
    for idx in range(3, sheet.nrows):
        station = str(sheet.cell_value(idx, 2)).strip()
        area = normalize(sheet.cell_value(idx, 0))
        if not station and area:
            finish_district()
            district = area
            expected = [integer(v) for v in sheet.row_values(idx)[3:end+7]]
            if len(expected) != n+7:
                raise ValueError('District row does not match candidate count')
            check_counts(expected, n)
            district_totals = [0] * (n+7)
            continue
        if not station:
            continue
        if expected is None or district is None:
            raise ValueError('Precinct without district header')
        station_id = integer(station)
        if station_id in seen:
            raise ValueError('Duplicate precinct number in election: '+str(station_id))
        seen.add(station_id)
        values = [integer(v) for v in sheet.row_values(idx)[3:end+7]]
        if len(values) != n+7:
            raise ValueError('Precinct column count mismatch')
        inventory_delta = check_counts(values,n)
        district_totals = [a+b for a,b in zip(district_totals,values)]
        precincts.append({
            'precinct_number':station_id, 'district':district,
            'candidate_votes':dict(zip(names,values[:n])),
            'valid_votes':values[n], 'invalid_votes':values[n+1],
            'ballots_cast':values[n+2], 'issued_or_used_plus_unused':values[n+4],
            'electorate':values[n+6],
            'turnout_rate':values[n+2]/values[n+6] if values[n+6] else None,
            'inventory_delta':inventory_delta,
            'source_sheet_row':idx+1
        })
    finish_district()
    if not precincts:
        raise ValueError('No individual precinct rows discovered')
    return {'candidate_names':names,'districts':districts,'precincts':precincts}


def convert_archives(folder,county_history,outdir):
    import xlrd
    audited=json.loads(Path(county_history).read_text(encoding='utf-8'))
    if audited.get('schema_version') != 1 or len(audited.get('races',[]))!=66:
        raise ValueError('Expected 66 previously audited county races')
    originals={(r['year'],r['county']):r for r in audited['races']}
    result=[]
    pending=[]
    processed=set()
    for filename,year in ARCHIVES.items():
        path=Path(folder)/filename
        if not path.is_file():
            raise FileNotFoundError('Original CEC ZIP is not available: '+str(path))
        raw=path.read_bytes()
        sha=hashlib.sha256(raw).hexdigest()
        matching=next((x for x in audited['source']['archives'] if x['filename']==filename),None)
        if not matching or matching['sha256']!=sha:
            raise ValueError('Original ZIP SHA256 differs from audited source: '+filename)
        for member,content in members(raw,filename):
            special=filename.startswith('1275') and '/表2-' in member
            if not member.lower().endswith('.xls') or not (special or '縣表3-1-' in member):
                continue
            if special:
                pending.append({'year':year,'county':'嘉義市','reason':'supplied_special_workbook_has_district_rows_only','source_locator':member})
                continue
            m=re.search(r'\(([^)]+)\)',member.rsplit('/',1)[-1])
            if not m:
                raise ValueError('Cannot resolve county in original worksheet: '+member)
            county=normalize(m.group(1))
            key=(year,county)
            if key in processed:
                raise ValueError('Duplicate county-year CEC precinct source '+str(key))
            if key not in originals:
                raise ValueError('No previously verified county total for '+str(key))
            workbook=xlrd.open_workbook(file_contents=content)
            parsed=parse_precinct_sheet(workbook.sheet_by_index(0))
            source=originals[key]
            # All numbers must reconcile to audited original municipal totals.
            fields=('valid_votes','invalid_votes','ballots_cast','electorate')
            sums={name:sum(p[name] for p in parsed['precincts']) for name in fields}
            if any(sums[name]!=source[name] for name in fields):
                raise ValueError(f'Precinct-to-county turnout reconciliation failed: {key} {sums}')
            candidate_by_name={c['name']:c['votes'] for c in source['candidates']}
            # CEC workbook candidate text can contain private-use glyphs.
            # Reconcile by ballot-number/order rather than repaired spelling.
            observed=[sum(p['candidate_votes'][n] for p in parsed['precincts'])
                      for n in parsed['candidate_names']]
            expected=[c['votes'] for c in sorted(source['candidates'],
                      key=lambda c:c['ballot_number'])]
            if observed!=expected:
                raise ValueError('Candidate vote rollup mismatch: '+str(key))
            record={
                'schema_version':1,'year':year,'county':county,
                'source_kind':'user_supplied_cec_original_precinct_xls',
                'source_zip_sha256':sha,'source_table_sha256':hashlib.sha256(content).hexdigest(),
                'source_locator':member,'precinct_count':len(parsed['precincts']),
                'district_count':len(parsed['districts']),
                'candidate_names':parsed['candidate_names'],
                'districts':parsed['districts'],'precincts':parsed['precincts'],
                'county_totals':sums,
                'warnings':{'nonzero_inventory_deltas':sum(bool(p['inventory_delta'])
                    for p in parsed['precincts'])},
                'publication_warning':'Historical station numbers are not stable geocodes. No cross-year station identity join or 2026 extrapolation.'
            }
            payload=json.dumps(record,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n'
            file=f'{year}-{county}.json'
            result.append({'year':year,'county':county,'path':'precinct/'+file,
                           'precinct_count':len(parsed['precincts']),
                           'district_count':len(parsed['districts']),
                           'sha256':hashlib.sha256(payload.encode('utf-8')).hexdigest(),
                           'nonzero_inventory_deltas':record['warnings']['nonzero_inventory_deltas'],
                           'county_totals':sums})
            processed.add(key)
            (Path(outdir)/'precinct').mkdir(parents=True,exist_ok=True)
            (Path(outdir)/'precinct'/file).write_text(payload,encoding='utf-8')
    expected=set(originals)
    pending_unique={(p['year'],p['county']) for p in pending}
    absent=expected-processed-pending_unique
    if absent:
        raise ValueError('Missing audited precinct source for '+repr(sorted(absent)))
    index={
        'schema_version':1,'source':'Original uploaded CEC Excel workbooks already verified in candidate-history-cec.json',
        'source_status':'precinct_where_original_xls_provides_precinct_rows',
        'coverage':{'county_elections_with_station_detail':len(result),
                    'county_elections_missing_station_detail':len(pending_unique),
                    'county_elections_total':len(expected),
                    'station_rows':sum(x['precinct_count'] for x in result)},
        'missing':pending,'files':sorted(result,key=lambda r:(r['year'],r['county'])),
        'join_warning':'Do not join raw station numbers across years: geographic precinct boundaries and booth IDs can change.',
        'ecological_warning':'Turnout at the station level does not identify individual voters or their candidate choices; not causal.',
        'forecast_status':'historical_research_only'
    }
    Path(outdir).mkdir(parents=True,exist_ok=True)
    (Path(outdir)/'precinct-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return index


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--folder',type=Path,required=True,help='Original 7 user-supplied CEC zip archives; no synthetic input')
    ap.add_argument('--county-history',type=Path,default=ROOT/'data/candidate-history-cec.json')
    ap.add_argument('--output',type=Path,default=ROOT/'data/cec-precinct-extract')
    opts=ap.parse_args()
    summary=convert_archives(opts.folder,opts.county_history,opts.output)
    print(json.dumps({'covered':summary['coverage'],'missing':summary['missing']},ensure_ascii=False))
