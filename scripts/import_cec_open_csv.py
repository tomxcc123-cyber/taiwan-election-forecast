"""Reconcile CEC official voteData ZIP polling-place rows to the audited 66 mayoral races.

No political-party preference assumptions. Only historical voters, cast/valid/
invalid ballots and observed recorded votes. Fail closed on missing/contradictory
sources; do not join polling-station IDs across election years.
"""
import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://data.cec.gov.tw/選舉資料庫/votedata.zip'
YEARS = (2014, 2018, 2022)
FIELDS = ('valid_votes','invalid_votes','ballots_cast','electorate')


def dequote(text):
    return str(text or '').strip().lstrip("'").replace('臺','台')


def numeric(text):
    value=dequote(text)
    if not value.isdigit():
        raise ValueError('Expected nonnegative integer in official CEC table: '+repr(text))
    return int(value)


def rows_from_bytes(raw):
    data=raw.decode('utf-8-sig')
    return list(csv.reader(io.StringIO(data, newline='')))


def zone_key(row):
    if len(row)<6:raise ValueError('Malformed CEC geographic tuple')
    return tuple(dequote(x).zfill(n) for x,n in zip(row[:6],(2,3,2,3,4,4)))


def county_key(row):
    return zone_key(row)[:2]


def pick_paths(z):
    """Only mayoral election tables; never mix council/presidential files."""
    found=defaultdict(dict)
    for name in z.namelist():
        if not name.lower().endswith('.csv') or not any(name.endswith('/'+x) for x in
            ('elbase.csv','elprof.csv','elctks.csv')):
            continue
        year=next((y for y in YEARS if f'/{y}-' in name),None)
        if year is None:continue
        parts=name.split('/')
        if year in (2014,2018):
            if not any(segment in ('直轄市市長','縣市市長') for segment in parts):
                continue
        elif not any(x in name for x in ('/C1/','/D1/','/D2/')):
            continue
        folder=name.rsplit('/',1)[0]
        found[(year,folder)][name.rsplit('/',1)[1]]=name
    return {k:v for k,v in found.items() if {'elbase.csv','elprof.csv','elctks.csv'}.issubset(v)}


def collect_profile_groups(z,year,files):
    raw={k:z.read(v) for k,v in files.items()}
    geonames={}
    for r in rows_from_bytes(raw['elbase.csv']):
        if len(r)>=6 and dequote(r[3])=='000' and dequote(r[4])=='0000' and dequote(r[2])=='00':
            name=dequote(r[5])
            if name:
                geonames[tuple(dequote(x).zfill(n) for x,n in zip(r[:2],(2,3)))]=name
    groups=defaultdict(list)
    totals={}
    for r in rows_from_bytes(raw['elprof.csv']):
        if len(r)<11:continue
        k=county_key(r)
        if k not in geonames:continue
        meta={'valid_votes':numeric(r[6]),'invalid_votes':numeric(r[7]),
            'ballots_cast':numeric(r[8]),'electorate':numeric(r[9])}
        # CEC station number zero indicates county or intermediate subtotal.
        station=zone_key(r)[5]
        if station=='0000' and all(zone_key(r)[i]=='0'*n for i,n in [(2,2),(3,3),(4,4)]):
            totals[k]=meta
        elif station!='0000':
            groups[k].append((r,meta))
    return raw,geonames,groups,totals


def convert(zip_path,history_path,output_path):
    audited=json.loads(Path(history_path).read_text(encoding='utf-8'))
    if len(audited.get('races',[]))!=66:raise ValueError('Expected 66 audited mayoral races')
    official={(r['year'],r['county']):r for r in audited['races']}
    output=Path(output_path)
    output.mkdir(parents=True,exist_ok=True)
    entries=[]
    with ZipFile(zip_path) as z:
        inventory=pick_paths(z)
        if len(inventory)<6:raise ValueError('Official CEC archive missing historical mayoral election CSV tables')
        sources=[]
        for (year,folder),files in inventory.items():
            raw,names,groups,totals=collect_profile_groups(z,year,files)
            # File-level rows containing other elections can be a candidate source
            # only when all 4 audited county aggregates agree exactly.
            sources.append((year,folder,files,raw,names,groups,totals))
        target_coverage=defaultdict(list)
        for year,folder,files,raw,names,groups,totals in sources:
            for k,name in names.items():
                target=official.get((year,name))
                if not target or k not in totals:continue
                if all(totals[k][field]==target[field] for field in FIELDS):
                    target_coverage[(year,name)].append((folder,k,files,raw,groups))
        for key,target in sorted(official.items()):
            year,county=key
            matches=target_coverage.get(key,[])
            if len(matches)>1:
                # Two official files describing the same race can be duplicates.
                # Keep only if their polling-place tuples are byte-identical.
                signatures=[]
                for folder,k,files,raw,groups in matches:
                    h=hashlib.sha256(json.dumps([(zone_key(r),p) for r,p in groups[k]],
                        sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                    signatures.append(h)
                if len(set(signatures))!=1:
                    raise ValueError('Ambiguous disagreeing CEC CSV precinct sources: '+str(key))
            if not matches:
                if target['source']['checks'].get('level')=='county_and_district':
                    entries.append({'year':year,'county':county,'status':'district_only_original',
                        'precinct_count':0,'reason':'original verified CEC workbook only had district subtotals'})
                    continue
                raise ValueError('Missing matching official mayoral station data: '+str(key))
            folder,code,files,raw,groups=matches[0]
            stations=groups[code]
            if not stations:raise ValueError('CEC aggregate lacks station rows for '+str(key))
            seen=set()
            packed=[]
            summed=defaultdict(int)
            for line,meta in stations:
                geo=zone_key(line)
                if geo in seen:raise ValueError('Duplicate CEC official station key '+str((key,geo)))
                seen.add(geo)
                if meta['valid_votes']+meta['invalid_votes']!=meta['ballots_cast'] or
                    meta['electorate']<meta['ballots_cast']:
                    raise ValueError('Vote conservation fails for '+str((key,geo)))
                for field in FIELDS:summed[field]+=meta[field]
                packed.append({'geo_codes':list(geo),'precinct_number':geo[5],
                    **meta,
                    'turnout_rate':meta['ballots_cast']/meta['electorate'] if meta['electorate'] else None})
            if any(summed[field]!=target[field] for field in FIELDS):
                raise ValueError('Official per-station sums differ from previously audited original: '+str(key))
            # A small immutable local file is loaded on demand by county/year, not
            # a giant bulk archive in every browser page load.
            record={'schema_version':1,'year':year,'county':county,
                'source':'CEC official open-data votedata.zip / elprof.csv',
                'source_url':URL,'source_member':files['elprof.csv'],
                'source_member_sha256':hashlib.sha256(raw['elprof.csv']).hexdigest(),
                'race_id':target['race_id'],'totals':dict(summed),
                'precinct_count':len(packed),'precincts':packed,
                'identity_warning':'Station number and village codes are observed geography for this election only; cross-year booth IDs must NOT be joined directly.',
                'analysis_status':'observed_2014_2018_2022_only_not_2026_forecast'}
            name=f'{year}-{county}.json'
            data=json.dumps(record,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n'
            (output/name).write_text(data,encoding='utf-8')
            entries.append({'year':year,'county':county,'status':'official_precinct_aggregate_verified',
                'path':'cec-precincts/'+name,'precinct_count':len(packed),
                'totals':dict(summed),
                'sha256':hashlib.sha256(data.encode()).hexdigest()})
    statuses=defaultdict(int)
    for entry in entries:statuses[entry['status']]+=1
    result={'schema_version':1,'source_url':URL,
        'source_kind':'cec_official_bulk_votedata',
        'levels':'individual polling-station aggregate, NOT voter-level',
        'years':list(YEARS),'coverage':dict(statuses),
        'station_rows':sum(x.get('precinct_count',0) for x in entries),
        'races_expected':66,'races_found':len(entries),
        'ecological_warning':'Aggregated booth turnout cannot reveal individual voting preferences and cannot justify targeting or causal claims.',
        'join_warning':'No direct cross-year station join; booth and administrative boundaries may change.',
        'forecast_status':'historical_study_only', 'entries':entries}
    if len(entries)!=66:raise ValueError('Missing 66 audited county-year elections')
    (output/'index.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--zip',type=Path,required=True)
    ap.add_argument('--history',type=Path,default=ROOT/'data/candidate-history-cec.json')
    ap.add_argument('--output',type=Path,default=ROOT/'data/cec-precincts')
    options=ap.parse_args()
    result=convert(options.zip,options.history,options.output)
    print(json.dumps({'coverage':result['coverage'],
      'station_rows':result['station_rows'],
      'entries':len(result['entries'])},ensure_ascii=False))
