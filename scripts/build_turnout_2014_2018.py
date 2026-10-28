"""Construct independently audited 2014→2018 town turnout from original CEC elbase.

2014 polling-place elprof uses ballot electoral-area 01, whereas official
elbase administrative town labels use area 00. We reconcile the name WITHIN
the original 2014 election folder using the observed county + town code, not
the 2018 labels or the station identifier. If 2014 original labels cannot
resolve uniquely, exclude the district, never retroactively backfill.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

try:
    from scripts.import_cec_open_csv import dequote,rows_from_bytes
except ImportError:
    from import_cec_open_csv import dequote,rows_from_bytes

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('electorate','ballots_cast','valid_votes','invalid_votes')

def admin_names(original_elbase):
    names=defaultdict(set)
    for line in rows_from_bytes(original_elbase):
        if len(line)<6:continue
        province,county,area,town,village=[dequote(v) for v in line[:5]]
        name=dequote(line[5]).strip()
        if area!='00' or town=='000' or village!='0000' or not name:
            continue
        if not name.endswith(('區','鎮','鄉','市')) or '選區' in name:
            continue
        names[(province.zfill(2),county.zfill(3),town.zfill(3))].add(name)
    return {k:next(iter(v)) for k,v in names.items() if len(v)==1},sum(len(v)>1 for v in names.values())


def audited_town_rollup(record,entry,labels=None):
    if not isinstance(record.get('precincts'),list) or len(record['precincts'])!=entry['precinct_count']:
        raise ValueError('CEC booth file truncated')
    if record['year']!=entry['year'] or record['county']!=entry['county']:
        raise ValueError('CEC booth record mismatch')
    groups=defaultdict(lambda:{'code':'','name':'','stations':0,
        **{f:0 for f in FIELDS}})
    totals={f:0 for f in FIELDS}
    missing=set()
    seen=set()
    for station in record['precincts']:
        geo=station.get('geo_codes')
        if not isinstance(geo,list) or len(geo)!=6 or any(not isinstance(v,str) for v in geo):
            raise ValueError('Malformed 2014/2018 CEC station tuple')
        station_key=tuple(geo)
        if station_key in seen:raise ValueError('Duplicate station tuple')
        seen.add(station_key)
        for f in FIELDS:
            if type(station.get(f)) is not int or station[f]<0:raise ValueError('Non-integer vote counts')
            totals[f]+=station[f]
        if station['valid_votes']+station['invalid_votes']!=station['ballots_cast'] or station['ballots_cast']>station['electorate']:
            raise ValueError('CEC station vote conservation fails')
        key=(geo[0],geo[1],geo[3])
        name=labels.get(key) if labels is not None else station.get('district_name')
        if not name:
            missing.add(key)
            continue
        name=dequote(name).strip()
        g=groups[key]
        if g['name'] and g['name']!=name:raise ValueError('Conflicting district labels in original CEC')
        g['code']='/'.join(key)
        g['name']=name
        g['stations']+=1
        for f in FIELDS:g[f]+=station[f]
    if any(totals[f]!=entry['totals'][f] or totals[f]!=record['totals'][f] for f in FIELDS):
        raise ValueError('CEC county totals not equal to sum of archived stations')
    for k,g in groups.items():
        if k in missing:
            raise ValueError('Partially labeled official district: '+str(k))
        if g['electorate']<=0 or g['ballots_cast']<=0:raise ValueError('CEC district denominator empty')
    return groups,missing


def build(zip_path,source_root,history_path):
    source_root=Path(source_root)
    ix=json.loads((source_root/'index.json').read_text(encoding='utf8'))
    history=json.loads(Path(history_path).read_text(encoding='utf8'))
    if len(ix.get('entries',[]))!=66 or len(history.get('races',[]))!=66:
        raise ValueError('Not 66 independently audited CEC races')
    audited={(r['year'],r['county']):r for r in history['races']}
    entries={(e['year'],e['county']):e for e in ix['entries']}
    all_counties=sorted({e['county'] for e in ix['entries']})
    if len(all_counties)!=22:raise ValueError('Expected 22 historical counties')
    output=[]
    with ZipFile(zip_path) as z:
        for county in all_counties:
            years={}
            for y in (2014,2018):
                entry=entries[(y,county)]
                if entry['status']!='official_precinct_aggregate_verified':
                    years[y]={'status':'not_verified'};continue
                path=source_root/Path(entry['path']).name
                raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=entry['sha256']:
                    raise ValueError('Archived source hash does not match CEC index '+str(path))
                record=json.loads(raw)
                official=audited[(y,county)]
                if any(record['totals'][f]!=official[f] for f in FIELDS):
                    raise ValueError('Official audited workbook county total mismatch')
                name_source=None
                if y==2014:
                    source_member=record['source_member'].rsplit('/',1)[0]+'/elbase.csv'
                    if source_member not in z.namelist():
                        raise ValueError('Original 2014 CEC administrative key source missing '+source_member)
                    original=z.read(source_member)
                    names,ambiguous=admin_names(original)
                    name_source={'source_member':source_member,
                        'sha256':hashlib.sha256(original).hexdigest(),
                        'ambiguous_town_codes':ambiguous,
                        'mapping_policy':'ONLY original year-2014 elbase area=00 town names. 2014 station electoral area may differ.'}
                    if ambiguous:raise ValueError('Ambiguous CEC original admin names')
                else:names=None
                towns,missing=audited_town_rollup(record,entry,names)
                years[y]={'status':'verified','towns':towns,
                          'missing_town_codes':[list(x) for x in sorted(missing)],
                          'original_admin_source':name_source}
            old,new=years[2014],years[2018]
            reasons=[]
            matched=[]
            if old['status']!='verified' or new['status']!='verified':
                reasons.append('原始逐站資料未核驗')
            else:
                old_by_code={k[2]:v for k,v in old['towns'].items()}
                new_by_code={k[2]:v for k,v in new['towns'].items()}
                for code in sorted(set(old_by_code)&set(new_by_code)):
                    a,b=old_by_code[code],new_by_code[code]
                    if a['name']!=b['name']:continue
                    matched.append({'town_code':code,'district':b['name'],
                        'join_policy':'same official 2014 and 2018 town code and original name; station codes NOT matched',
                        'years':{str(y):{f:rec[f] for f in (*FIELDS,'stations')}
                                 for y,rec in ((2014,a),(2018,b))},
                        'delta_turnout_pp':round(100*(b['ballots_cast']/b['electorate']-
                                                       a['ballots_cast']/a['electorate']),5)})
                if not matched:reasons.append('無可核對的同碼同名行政區')
            represented=sum(t['years']['2018']['electorate'] for t in matched)
            total_2018=audited[(2018,county)]['electorate']
            output.append({'county':county,
                'status':'matched_original_code_name' if matched else 'excluded',
                'exclusion_reasons':reasons,
                'matched_towns':len(matched),
                '2018_electorate_coverage':round(represented/total_2018,6),
                '2014_label_source':old.get('original_admin_source'),
                '2014_unlabeled_town_codes':old.get('missing_town_codes',[]),
                '2014_original_district_count':len(old.get('towns',{})),
                '2018_original_district_count':len(new.get('towns',{})),
                'unmatched_2014_names':[v['name'] for k,v in old.get('towns',{}).items()
                    if not any(t['district']==v['name'] and t['town_code']==k[2] for t in matched)],
                'unmatched_2018_names':[v['name'] for k,v in new.get('towns',{}).items()
                    if not any(t['district']==v['name'] and t['town_code']==k[2] for t in matched)],
                'districts':matched})
    return {
       'schema_version':1,'kind':'observed_cec_2014_to_2018_town_turnout_holdout_input',
       'source_url':ix['source_url'],
       'verification':'2014 original elbase names; 2014/2018 source-hashed elprof booth totals and independently audited county mayoral counts',
       'years':[2014,2018],
       'matched_counties':sum(x['status']=='matched_original_code_name' for x in output),
       'matched_towns':sum(x['matched_towns'] for x in output),
       'excluded_counties':[x['county'] for x in output if x['status']=='excluded'],
       'no_cross_year_precinct_join':True,
       'join_screen_not_boundary_proof':True,
       'no_individual_voter_inference':True,
       'official_2026_forecast_unchanged':True,
       'counties':output
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--zip',type=Path,required=True)
    p.add_argument('--source',type=Path,default=ROOT/'data/cec-precincts')
    p.add_argument('--history',type=Path,default=ROOT/'data/candidate-history-cec.json')
    p.add_argument('--output',type=Path,default=ROOT/'data/turnout-district-panel-2014-2018.json')
    a=p.parse_args()
    report=build(a.zip,a.source,a.history)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'matched_counties':report['matched_counties'],
        'matched_towns':report['matched_towns'],
        'excluded_counties':report['excluded_counties'],
        'taipei':next(({'district_count':c['matched_towns'],
                        '2018_electorate_coverage':c['2018_electorate_coverage'],
                        '2014_label_source':c['2014_label_source']}
             for c in report['counties'] if c['county']=='台北市'),None)},ensure_ascii=False))


if __name__=='__main__':main()
