"""Audit historic CEC station candidate votes and aggregate to matched towns.

Uses official elctks.csv only in the verified mayoral election folder that
produced each audited station profile. Candidate ballot order and every
station/district/county total must reconcile. No inference of individual
preferences or causal effect of voter participation is made.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

try:
    from scripts.import_cec_open_csv import URL, zone_key, rows_from_bytes, numeric
except ImportError:
    from import_cec_open_csv import URL, zone_key, rows_from_bytes, numeric

ROOT=Path(__file__).resolve().parents[1]
YEARS=(2018,2022)
BLOCS=('KMT','DPP')

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf8'))

def parse_station_votes(raw,station_keys,valid_by_station,candidates):
    """Integer ballots per actual station keyed by six CEC geography fields."""
    expected={int(c['ballot_number']):c for c in candidates}
    if len(expected)!=len(candidates) or min(expected)!=1 or max(expected)!=len(expected):
        raise ValueError('Ambiguous CEC candidate ballot order')
    station_votes=defaultdict(dict)
    for r in rows_from_bytes(raw):
        if len(r)<8:continue
        geo=zone_key(r)
        if geo not in station_keys:continue # Ignore county/district/village totals.
        number=numeric(r[6]);value=numeric(r[7])
        if number not in expected:
            raise ValueError('Unknown CEC candidate number '+str(number))
        if number in station_votes[geo]:
            raise ValueError('Duplicate candidate ballot row at station')
        station_votes[geo][number]=value
    if len(station_votes)!=len(station_keys):
        raise ValueError('Missing station candidate-vote records')
    for geo in station_keys:
        votes=station_votes[geo]
        if len(votes)!=len(expected) or sum(votes.values())!=valid_by_station[geo]:
            raise ValueError('Candidate/station valid-vote conservation failed: '+str(geo))
    totals={number:sum(station_votes[geo][number] for geo in station_keys)
            for number in expected}
    for number,c in expected.items():
        if totals[number]!=c['votes']:
            raise ValueError('Official candidate total diverges from audited history: '
                             +str((number,c['name'],totals[number],c['votes'])))
    return station_votes,expected

def build(zip_path,stations_root,history_path,turnout_path):
    index=read_json(Path(stations_root)/'index.json')
    history=read_json(history_path)
    panel=read_json(turnout_path)
    if len(index.get('entries',[]))!=66 or len(history.get('races',[]))!=66 or len(panel.get('counties',[]))!=22:
        raise ValueError('Incomplete verified CEC input')
    official={(x['year'],x['county']):x for x in history['races']}
    entries={(x['year'],x['county']):x for x in index['entries']}
    records={}
    with ZipFile(zip_path) as z:
        for (year,county),entry in sorted(entries.items()):
            if year not in YEARS:continue
            if entry['status']!='official_precinct_aggregate_verified':
                continue
            path=Path(stations_root)/Path(entry['path']).name
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=entry['sha256']:
                raise ValueError('Profile station source hash mismatch')
            stations=read_json(path)
            audited=official[(year,county)]
            if audited['valid_votes']!=stations['totals']['valid_votes']:
                raise ValueError('County valid-vote total mismatch')
            keys={tuple(s['geo_codes']):s for s in stations['precincts']}
            source=stations['source_member'].rsplit('/',1)[0]+'/elctks.csv'
            if source not in z.namelist():
                raise ValueError('Original official CEC candidate CSV missing '+source)
            votes,ballots=parse_station_votes(z.read(source),keys,
                {k:s['valid_votes'] for k,s in keys.items()},audited['candidates'])
            grouped=defaultdict(lambda:{'valid_votes':0,'ballots_cast':0,
                'electorate':0,'candidate_votes':defaultdict(int)})
            for geo,s in keys.items():
                district='/'.join(geo[:4])
                g=grouped[district]
                for item in ('valid_votes','ballots_cast','electorate'):
                    g[item]+=s[item]
                for number,v in votes[geo].items():
                    g['candidate_votes'][number]+=v
            groups={}
            for district,d in grouped.items():
                if sum(d['candidate_votes'].values())!=d['valid_votes']:
                    raise ValueError('Town candidate vote accounting failed')
                groups[district]={
                    'valid_votes':d['valid_votes'],
                    'ballots_cast':d['ballots_cast'],
                    'electorate':d['electorate'],
                    'candidate_votes':{str(n):d['candidate_votes'][n] for n in sorted(ballots)},
                    'bloc_votes':{bloc:sum(d['candidate_votes'][n] for n,c in ballots.items()
                                          if c['legacy_bloc']==bloc) for bloc in BLOCS}
                }
            if sum(g['valid_votes'] for g in groups.values())!=audited['valid_votes']:
                raise ValueError('County candidate-district rollup failed')
            records[(year,county)]={
                'candidate_manifest':[{'ballot_number':n,'candidate_id':c['candidate_id'],
                     'name':c['name'],'legacy_bloc':c['legacy_bloc'],'votes':c['votes']}
                    for n,c in sorted(ballots.items())],
                'source_elctks_sha256':hashlib.sha256(z.read(source)).hexdigest(),
                'source_elctks_member':source,
                'districts':groups
            }
    output_counties=[]
    matched_districts=0
    compatible_bloc_count=0
    station_count=0
    for source_county in panel['counties']:
        county=source_county['county']
        result={'county':county,'status':'excluded','excluded_reasons':[],
                'districts':[],'source_coverage':source_county['status']}
        left=records.get((2018,county));right=records.get((2022,county))
        if source_county['status']!='matched_code_name_only' or not left or not right:
            result['excluded_reasons'].append('原始2018/2022選舉逐站候選人資料或行政區對應缺失')
            output_counties.append(result);continue
        result['source_files']={
            str(y):{'elctks_sha256':r['source_elctks_sha256'],
                    'elctks_member':r['source_elctks_member'],
                    'candidates':r['candidate_manifest']}
            for y,r in [(2018,left),(2022,right)]}
        manifests={year:rec['candidate_manifest'] for year,rec in [(2018,left),(2022,right)]}
        has_competition=all(
            all(any(c['legacy_bloc']==bloc for c in manifests[year]) for bloc in BLOCS)
            for year in YEARS)
        for town in source_county['districts']:
            key=town['district_code']
            old=left['districts'].get(key);new=right['districts'].get(key)
            if old is None or new is None:
                raise ValueError('Missing audited matched town candidate votes')
            for year,r,x in [(2018,old,town['years']['2018']),(2022,new,town['years']['2022'])]:
                if any(r[f]!=x[f] for f in ('valid_votes','ballots_cast','electorate')):
                    raise ValueError('Candidate town and turnout source mismatch: '+str((county,year,key)))
            measured={}
            for year,record in [(2018,old),(2022,new)]:
                k,d=record['bloc_votes']['KMT'],record['bloc_votes']['DPP']
                denom=k+d
                measured[str(year)]={
                    'candidate_votes':record['candidate_votes'],
                    'valid_votes':record['valid_votes'],
                    'KMT_votes':k,'DPP_votes':d,
                    'KMT_two_party_share_pct':100*k/denom if has_competition and denom else None,
                    'two_party_count':denom
                }
            obs=measured['2018']['KMT_two_party_share_pct']
            current=measured['2022']['KMT_two_party_share_pct']
            # Only compare the same named party blocs when both contested both
            # elections. This does not assert equal candidate quality or electorate.
            paired=obs is not None and current is not None
            result['districts'].append({
                'district':town['district'],'district_code':key,
                'delta_turnout_pp':town['delta_turnout_pp'],
                'party_comparison_eligible':paired,
                'delta_KMT_two_party_share_pp':round(current-obs,5) if paired else None,
                'years':measured
            })
            matched_districts+=1
            if paired:compatible_bloc_count+=1
        result['status']='audited_historical_town_observation'
        result['candidate_contest_compatible']=has_competition
        result['matched_districts']=len(result['districts'])
        output_counties.append(result)
    if matched_districts!=panel['matched_districts']:
        raise ValueError('Candidate turnout linkage did not cover all matched districts')
    return {
        'schema_version':1,'kind':'historical_ecological_candidate_turnout_association_only',
        'years':list(YEARS),'source_url':URL,
        'counties':output_counties,
        'matched_towns':matched_districts,
        'party_comparable_towns':compatible_bloc_count,
        'matched_counties':sum(x['status']=='audited_historical_town_observation' for x in output_counties),
        'outcome':'2018→2022 change in KMT two-party share only when KMT and DPP both fielded candidates in each year',
        'party_mapping':'audited original candidate legacy_bloc, never inferred from precinct turnout',
        'no_causal_claim':True,'no_2026_prediction':True,
        'official_forecast_unchanged':True,
        'limits':'Ecological data; candidate quality, incumbency, demographic change and common causes confound trends. No independently calibrated turnout-to-candidate mechanism.'
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--zip',type=Path,required=True)
    p.add_argument('--stations',type=Path,default=ROOT/'data/cec-precincts')
    p.add_argument('--history',type=Path,default=ROOT/'data/candidate-history-cec.json')
    p.add_argument('--panel',type=Path,default=ROOT/'data/turnout-district-panel-2018-2022.json')
    p.add_argument('--output',type=Path,default=ROOT/'data/cec-town-candidate-association-2018-2022.json')
    args=p.parse_args()
    report=build(args.zip,args.stations,args.history,args.panel)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'matched_towns':report['matched_towns'],
        'party_comparable_towns':report['party_comparable_towns'],
        'matched_counties':report['matched_counties']},ensure_ascii=False))

if __name__=='__main__':main()
