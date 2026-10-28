"""Observed 2018→2022 township turnout panels from verified CEC booth chunks.

Stable *code and label* matching is a screening rule, NOT proof that village
boundaries or the electorate composition were unchanged. Candidate support
effects are deliberately not estimated from aggregate turnout observations.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('electorate','ballots_cast','valid_votes','invalid_votes')
YEARS=(2018,2022)

def name_norm(text):
    return str(text or '').strip().replace('臺','台').replace('　',' ')

def analyze_county_record(record,entry):
    if record.get('schema_version')!=1 or record.get('year')!=entry['year'] or record.get('county')!=entry['county']:
        raise ValueError('CEC archive year/county mismatch')
    stations=record.get('precincts',[])
    if len(stations)!=entry['precinct_count'] or not stations:
        raise ValueError('CEC precinct source truncated')
    rollup=defaultdict(lambda:dict(code='',name='',stations=0,
        electorate=0,ballots_cast=0,valid_votes=0,invalid_votes=0))
    county_sums={f:0 for f in FIELDS}
    seen=set()
    for station in stations:
        geo=station['geo_codes']
        if len(geo)!=6:raise ValueError('Unexpected station geographic keys')
        identity='/'.join(geo)
        if identity in seen:raise ValueError('Duplicate official booth key')
        seen.add(identity)
        code='/'.join(geo[:4])
        label=name_norm(station.get('district_name'))
        if not label: # never infer year-2014 names from later administrative boundaries
            raise ValueError('Official CEC district label missing: '+record['county']+' '+str(record['year']))
        if any(not isinstance(station.get(f),int) or station[f]<0 for f in FIELDS):
            raise ValueError('Invalid booth integer total')
        if station['valid_votes']+station['invalid_votes']!=station['ballots_cast'] or station['ballots_cast']>station['electorate']:
            raise ValueError('Invalid booth vote conservation')
        row=rollup[code]
        if row['name'] and row['name']!=label:raise ValueError('District code used with conflicting names')
        row['code']=code
        row['name']=label
        row['stations']+=1
        for f in FIELDS:
            row[f]+=station[f];county_sums[f]+=station[f]
    if any(county_sums[f]!=entry['totals'][f] or county_sums[f]!=record['totals'][f] for f in FIELDS):
        raise ValueError('Booth/district/county totals mismatch')
    for row in rollup.values():
        if row['electorate']==0 or row['ballots_cast']==0:
            raise ValueError('Empty administrative district')
        row['turnout_pct']=round(100*row['ballots_cast']/row['electorate'],4)
        row['invalid_pct']=round(100*row['invalid_votes']/row['ballots_cast'],4)
    return rollup,county_sums

def build_panel(source_root,county_history):
    index_path=Path(source_root)/'index.json'
    source=json.loads(index_path.read_text(encoding='utf8'))
    audited=json.loads(Path(county_history).read_text(encoding='utf8'))
    if source.get('schema_version')!=1 or len(source.get('entries',[]))!=66:
        raise ValueError('Unknown audited CEC precinct index')
    if len(audited.get('races',[]))!=66:
        raise ValueError('Unknown verified historical CEC mayoral count')
    by_race={(x['year'],x['county']):x for x in audited['races']}
    by_county=defaultdict(dict)
    for entry in source['entries']:
        if entry['year'] not in YEARS:continue
        year,county=entry['year'],entry['county']
        if entry['status']!='official_precinct_aggregate_verified':
            by_county[county][year]={'status':'missing','reason':entry['status']}
            continue
        path=Path(source_root)/Path(entry['path']).name
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:
            raise ValueError('CEC CSV derived file SHA256 mismatch: '+str(path))
        record=json.loads(raw)
        grouped,totals=analyze_county_record(record,entry)
        official=by_race.get((year,county))
        if not official or any(totals[f]!=official[f] for f in FIELDS):
            raise ValueError('District data disagrees with independently audited CEC original')
        by_county[county][year]={'status':'verified','districts':grouped,
                                'county_totals':totals}
    if len(by_county)!=22:raise ValueError('Expected 22 unique counties')
    counties=[]
    for county,years in sorted(by_county.items()):
        left,right=years.get(2018),years.get(2022)
        reasons=[]
        if not left or left['status']!='verified':reasons.append('2018逐站來源缺失')
        if not right or right['status']!='verified':reasons.append('2022逐站來源缺失或非同場投票')
        districts=[]
        left_only=[];right_only=[]
        if not reasons:
            l,r=left['districts'],right['districts']
            for k,v in l.items():
                if k not in r or v['name']!=r[k]['name']:
                    left_only.append({'code':k,'name':v['name']})
            for k,v in r.items():
                if k not in l or v['name']!=l[k]['name']:
                    right_only.append({'code':k,'name':v['name']})
            for key in sorted(set(l)&set(r)):
                old,new=l[key],r[key]
                if old['name']!=new['name']:continue
                delta=100*(new['ballots_cast']/new['electorate']-old['ballots_cast']/old['electorate'])
                districts.append({
                    'district_code':key,'district':new['name'],
                    'boundary_screen':'code_and_name_match_only',
                    'years':{str(y):{f:yr[f] for f in (*FIELDS,'stations','turnout_pct','invalid_pct')}
                           for y,yr in [(2018,old),(2022,new)]},
                    'delta_turnout_pp':round(delta,4),
                    'delta_invalid_pp':round(new['invalid_pct']-old['invalid_pct'],4),
                    'delta_electorate':new['electorate']-old['electorate'],
                    'delta_cast':new['ballots_cast']-old['ballots_cast']
                })
            if len(districts)==0:reasons.append('無具名同碼行政區')
        matched_eligible=sum(d['years']['2022']['electorate'] for d in districts)
        total_eligible=right['county_totals']['electorate'] if right and right['status']=='verified' else None
        coverage=matched_eligible/total_eligible if total_eligible else 0
        county_data={
            'county':county,'status':'matched_code_name_only' if districts and not reasons else 'excluded',
            'exclusion_reasons':reasons,'total_districts_2018':len(left.get('districts',{})) if left else 0,
            'total_districts_2022':len(right.get('districts',{})) if right else 0,
            'matched_districts':len(districts),
            'unmatched_2018':left_only,'unmatched_2022':right_only,
            '2022_matched_electorate_coverage':round(coverage,5),
            'county_observed_turnout_pp':({
                '2018':round(100*left['county_totals']['ballots_cast']/left['county_totals']['electorate'],4),
                '2022':round(100*right['county_totals']['ballots_cast']/right['county_totals']['electorate'],4)
            } if not reasons else None),
            'districts':districts}
        counties.append(county_data)
    districts=[d for c in counties for d in c['districts']]
    if not districts:raise ValueError('No matched administrative units')
    total2018=sum(c['total_districts_2018'] for c in counties)
    total2022=sum(c['total_districts_2022'] for c in counties)
    uncovered=[c['county'] for c in counties if c['status']=='excluded']
    return {
       'schema_version':1,'kind':'observed_turnout_district_panel_not_an_individual_turnout_model',
       'years':[2018,2022], 'source_url':source['source_url'],
       'source_precinct_rows':source['station_rows'],
       'source_coverage':source['coverage'],
       'matched_counties':sum(c['status']=='matched_code_name_only' for c in counties),
       'excluded_counties':uncovered,
       'matched_districts':len(districts),
       'total_districts_2018':total2018,'total_districts_2022':total2022,
       'screening_only':'Same code AND same district name in both years. This DOES NOT prove stable administrative geography; use with boundary review.',
       'analysis_limits':'Descriptive historical turnout differences, not candidate impacts, causal inference, voter-level matching or 2026 turnout forecast.',
       'not_voter_level':True,'official_forecast_unchanged':True,
       'counties':counties}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'data/cec-precincts')
    p.add_argument('--history',type=Path,default=ROOT/'data/candidate-history-cec.json')
    p.add_argument('--output',type=Path,default=ROOT/'data/turnout-district-panel-2018-2022.json')
    args=p.parse_args()
    report=build_panel(args.source,args.history)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'matched_counties':report['matched_counties'],
       'matched_districts':report['matched_districts'],
       'excluded_counties':report['excluded_counties'],
       'all_2018_districts':report['total_districts_2018'],
       'all_2022_districts':report['total_districts_2022']},ensure_ascii=False))

if __name__=='__main__':main()
