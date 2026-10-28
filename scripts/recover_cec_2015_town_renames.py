"""Restore only CEC-documented 2015 town→city title changes, never infer boundaries.

The 2014 panel did not pair 員林鎮→員林市 / 頭份鎮→頭份市 because names
differed. CEC 2015 minutes explicitly document both names, original 2014
elbase independently recorded their old names, and original CEC precinct
files supply booth totals for both years. Full year-2014 and year-2018
station rollups must reconcile before two extra *administrative-code*
matches enter historical research. This does not certify geometric stability.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('electorate','ballots_cast','valid_votes','invalid_votes')
RENAMES={
 ('彰化縣','100'):{
   'before':'員林鎮','after':'員林市','effective_date':'2015-08-08',
   'official_url':'https://www.chcg.gov.tw/TSO/yuanlin/07other/main.aspx?main_id=30945'},
 ('苗栗縣','050'):{
   'before':'頭份鎮','after':'頭份市','effective_date':'2015-10-05',
   'official_url':'https://www.chcg.gov.tw/HSO/changhua/01news/news_a_02.aspx?bull_id=195475'},
}
CEC_MINUTES='https://web.cec.gov.tw/api/file/d97c9325-90b2-44bc-a430-c43197e58ea0.pdf'
STATUS='matched_original_code_name_with_documented_2015_renames'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def audited_town(record,code,year):
    if record.get('year')!=year or not isinstance(record.get('precincts'),list):
        raise ValueError('Original CEC station source year mismatch')
    selected=[x for x in record['precincts'] if x.get('geo_codes',[None]*6)[3]==code]
    if not selected:raise ValueError('No original CEC stations for renamed town')
    expected={f:0 for f in FIELDS}
    seen=set()
    for station in selected:
        geo=station.get('geo_codes')
        if (not isinstance(geo,list) or len(geo)!=6 or
            geo[2]!=('01' if year==2014 else '00') or
            any(type(station.get(f)) is not int or station[f]<0 for f in FIELDS)):
            raise ValueError('CEC station geography or count invalid')
        if tuple(geo) in seen:raise ValueError('Duplicate CEC booth in title-change town')
        seen.add(tuple(geo))
        if station['valid_votes']+station['invalid_votes']!=station['ballots_cast'] or station['ballots_cast']>station['electorate']:
            raise ValueError('Township original CEC vote conservation failed')
        for f in FIELDS:expected[f]+=station[f]
    if expected['electorate']<=0:return None
    return {**expected,'stations':len(selected)}


def recover(prior,recent,archive_root=ROOT/'data/cec-precincts'):
    if (prior.get('schema_version')!=1 or prior.get('kind')!='observed_cec_2014_to_2018_town_turnout_holdout_input'
        or prior.get('official_2026_forecast_unchanged') is not True or prior.get('no_cross_year_precinct_join') is not True
        or recent.get('kind')!='observed_turnout_district_panel_not_an_individual_turnout_model'
        or recent.get('official_forecast_unchanged') is not True):
        raise ValueError('Unverified historical panel')
    ix=read(Path(archive_root)/'index.json')
    entries={(e['year'],e['county']):e for e in ix.get('entries',[])}
    if len(entries)!=66:raise ValueError('Incomplete original CEC polling-booth register')
    counties={c['county']:c for c in prior['counties']}
    newer={c['county']:c for c in recent['counties']}
    if len(counties)!=22 or len(newer)!=22:raise ValueError('Missing original CEC county')
    outcomes=[]
    for (county,code),rule in RENAMES.items():
        c=counties[county];t=newer[county]
        existing=[d for d in c['districts'] if d['town_code']==code]
        if len(existing)==1:
            row=existing[0]
            info=row.get('documented_name_change')
            if (row['district']!=rule['after'] or not isinstance(info,dict) or
                info.get('2014_original_name')!=rule['before'] or info.get('2018_name')!=rule['after'] or
                info.get('cec_minutes_url')!=CEC_MINUTES):
                raise ValueError('Existing renamed row has unverified provenance')
            outcomes.append({'county':county,'town_code':code,'already_reconciled':True})
            continue
        if existing:raise ValueError('Ambiguous historical town-code join')
        src=c.get('2014_label_source') or {}
        if not isinstance(src.get('sha256'),str) or len(src['sha256'])!=64:
            raise ValueError('Missing original 2014 elbase checksum')
        if (c['unmatched_2014_names']!=[rule['before']] or
            c['unmatched_2018_names']!=[rule['after']] or
            c['2014_original_district_count']!=len(c['districts'])+1 or
            c['2018_original_district_count']!=len(c['districts'])+1):
            raise ValueError('Original official 2014/2018 names do not uniquely document rename')
        candidates=[d for d in t['districts'] if d['district_code'].split('/')[-1]==code]
        if len(candidates)!=1 or candidates[0]['district']!=rule['after']:
            raise ValueError('Modern township code does not reconcile with CEC original')
        source={}
        for year in (2014,2018):
            entry=entries.get((year,county))
            if entry is None or entry['status']!='official_precinct_aggregate_verified':
                raise ValueError('Missing independently source-hashed CEC township booths')
            file=Path(archive_root)/Path(entry['path']).name
            raw=file.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=entry['sha256']:
                raise ValueError('Verified booth SHA-256 mismatch')
            record=json.loads(raw)
            if record['county']!=county or record['precinct_count']!=entry['precinct_count'] or record['totals']!=entry['totals']:
                raise ValueError('CEC original county-station evidence mismatch')
            if year==2014 and not record['source_member'].startswith('votedata/votedata/voteData/2014-'):
                raise ValueError('2014 is not original CEC archive release')
            source[year]=audited_town(record,code,year)
        current=candidates[0]['years']['2018']
        if any(current[k]!=source[2018][k] for k in (*FIELDS,'stations')):
            raise ValueError('2018 CEC historical town totals disagree with later panel')
        a,b=source[2014],source[2018]
        row={'town_code':code,'district':rule['after'],
             'join_policy':'exact CEC town code; 2014 original elbase name to CEC-documented 2015 town-to-city title change; NOT a historical geometry proof',
             'documented_name_change':{
               '2014_original_name':rule['before'],'2018_name':rule['after'],
               'effective_date':rule['effective_date'],'official_local_government_url':rule['official_url'],
               'cec_minutes_url':CEC_MINUTES,'spatial_boundary_verified':False,
               '2014_elbase_sha256':src['sha256'],
               'source_archived_cec_station_sha256':{
                 str(y):entries[(y,county)]['sha256'] for y in (2014,2018)}},
             'years':{str(y):source[y] for y in (2014,2018)},
             'delta_turnout_pp':round(100*(b['ballots_cast']/b['electorate']-
                                            a['ballots_cast']/a['electorate']),5)}
        c['districts'].append(row)
        c['districts'].sort(key=lambda d:d['town_code'])
        c['matched_towns']=len(c['districts'])
        c['unmatched_2014_names']=[]
        c['unmatched_2018_names']=[]
        c['2018_electorate_coverage']=round(
            sum(d['years']['2018']['electorate'] for d in c['districts'])/
            sum(d['years']['2018']['electorate'] for d in t['districts']),6)
        c['status']=STATUS
        outcomes.append({'county':county,'town_code':code,'already_reconciled':False,
                         '2014':a,'2018':b})
    prior['matched_towns']=sum(len(c['districts']) for c in counties.values())
    prior['documented_2015_name_changes_count']=len(RENAMES)
    prior['documented_2015_name_changes']=sorted([
        {'county':c,'town_code':code,**rule} for (c,code),rule in RENAMES.items()],
        key=lambda x:(x['county'],x['town_code']))
    note='; two 2015 officially documented town-to-city title changes matched by identical original CEC town code and audited booth totals'
    if note not in prior['verification']:prior['verification']+=note
    prior['no_historical_polygon_comparison']=True
    if prior['matched_towns']!=368:
        raise ValueError('Restored 2014→2018 panel not complete')
    return prior,outcomes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prior',type=Path,default=ROOT/'data/turnout-district-panel-2014-2018.json')
    p.add_argument('--recent',type=Path,default=ROOT/'data/turnout-district-panel-2018-2022.json')
    p.add_argument('--stations',type=Path,default=ROOT/'data/cec-precincts')
    p.add_argument('--output',type=Path,default=ROOT/'data/turnout-district-panel-2014-2018.json')
    a=p.parse_args()
    prior,outcomes=recover(read(a.prior),read(a.recent),a.stations)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(prior,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'recovered':outcomes,'total_2014_to_2018':prior['matched_towns'],
                      'spatial_polygon_verified':False},ensure_ascii=False))


if __name__=='__main__':main()
