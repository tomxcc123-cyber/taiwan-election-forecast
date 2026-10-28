"""Three-election CEC township continuity audit and matched-cohort sensitivity.

This joins ONLY identical official town codes and names; it does not overlay
historical township polygons and cannot establish boundary or voter stability.
The test-election electorate and station counts are POST-ELECTION diagnostics
and must NEVER enter a pre-election prediction feature or a cohort-selection
claim about forecasting gains. Original holdout forecast errors are reused.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNTS = ('electorate', 'ballots_cast', 'valid_votes', 'invalid_votes', 'stations')
METHODS = ('persistence', 'county_shrink_75', 'county_shrink_50')
COHORTS = ('common_towns', 'unchanged_station_count',
           'electorate_change_within_8pct', 'both_diagnostic_flags_clear')


def normalize(name):
    return str(name).strip().replace('臺', '台')


def checked_year(record):
    if not isinstance(record, dict):
        raise ValueError('Missing original CEC year values')
    if any(type(record.get(x)) is not int or record[x] < 0 for x in COUNTS):
        raise ValueError('Non-integer township source count')
    if (record['electorate'] <= 0 or record['stations'] <= 0 or
        record['ballots_cast'] > record['electorate'] or
        record['valid_votes'] + record['invalid_votes'] != record['ballots_cast']):
        raise ValueError('CEC vote conservation failed')
    return {x: record[x] for x in COUNTS}


def key(county, code, name):
    if not isinstance(code, str) or len(code) != 3 or not code.isdigit():
        raise ValueError('Invalid original administrative town code')
    return county, code, normalize(name)


def pair_index(panel, prior):
    idx = {}
    for county in panel['counties']:
        c = normalize(county['county'])
        for town in county['districts']:
            if prior:
                code = town['town_code']
                if county['status'] not in ('matched_original_code_name','matched_original_code_name_with_documented_2015_renames'):
                    raise ValueError('Unverified 2014 CEC town source')
            else:
                if county['status'] != 'matched_code_name_only':
                    raise ValueError('Unverified 2018/2022 town source')
                parts = town['district_code'].split('/')
                if len(parts) != 4 or parts[2] != '00':
                    raise ValueError('Unsupported official CEC township code')
                code = parts[3]
            k = key(c, code, town['district'])
            if k in idx:
                raise ValueError('Duplicate township historical join key')
            idx[k] = town
    return idx


def validate_sources(prior, recent, validation):
    if (prior.get('schema_version') != 1 or
        prior.get('kind') != 'observed_cec_2014_to_2018_town_turnout_holdout_input' or
        prior.get('official_2026_forecast_unchanged') is not True or
        prior.get('no_cross_year_precinct_join') is not True or
        recent.get('schema_version') != 1 or
        recent.get('kind') != 'observed_turnout_district_panel_not_an_individual_turnout_model' or
        recent.get('official_forecast_unchanged') is not True or
        len(prior.get('counties', [])) != 22 or
        len(recent.get('counties', [])) != 22):
        raise ValueError('Unverified original CEC district data')
    for c in prior['counties']:
        if c['status'] in ('matched_original_code_name','matched_original_code_name_with_documented_2015_renames'):
            original = c.get('2014_label_source') or {}
            sha = original.get('sha256')
            if (not isinstance(sha, str) or len(sha) != 64 or
                not all(d in '0123456789abcdef' for d in sha)):
                raise ValueError('Original 2014 elbase SHA256 missing')
    if (validation.get('schema_version') != 1 or
        validation.get('kind') != 'cec_two_independent_town_turnout_cycles_2014_2022' or
        validation.get('no_future_outcome_predictors') is not True or
        validation.get('candidate_vote_data_used') is not False or
        validation.get('promotion_gate', {}).get('status') != 'blocked' or
        validation['promotion_gate'].get('allow_2026_candidate_win_probability_modification') is not False or
        validation['promotion_gate'].get('formal_hb_tlef_unchanged') is not True):
        raise ValueError('Unsafe model promotion or incomplete historical holdout')
    cycles = validation.get('cycles', {})
    if (set(cycles) != {'2014_to_2018', '2018_to_2022'} or
        cycles['2014_to_2018'].get('training_election') != 2014 or
        cycles['2014_to_2018'].get('held_out_election') != 2018 or
        cycles['2018_to_2022'].get('training_election') != 2018 or
        cycles['2018_to_2022'].get('held_out_election') != 2022):
        raise ValueError('Historical tests were not chronologically held out')
    return cycles


def check_holdout(row, year, source, prior):
    expected_in = 100 * prior['ballots_cast'] / prior['electorate']
    expected_out = 100 * source['ballots_cast'] / source['electorate']
    if (row['training_year'] != year-4 or row['test_year'] != year or
        row['target_electorate'] != source['electorate'] or
        abs(row['input_turnout_pct'] - expected_in) > .00011 or
        abs(row['observed_turnout_pct'] - expected_out) > .00011 or
        not all(isinstance(row['errors_pp'].get(k), (int, float)) for k in METHODS)):
        raise ValueError('Frozen holdout diverged from audited original counts')


def score(rows, cycle):
    total = sum(x['target_electorate'] for x in rows)
    if not rows or total <= 0:
        return {'n_towns': 0, 'scores': None}
    metrics = {}
    for method in METHODS:
        mae = sum(x['target_electorate'] * abs(x['errors_pp'][method])
                  for x in rows) / total
        metrics[method] = round(mae, 5)
    return {'n_towns': len(rows), 'scores': metrics,
            'delta_75_vs_persistence_pp': round(
                metrics['county_shrink_75'] - metrics['persistence'], 5)}


def evaluate(prior, recent, validation):
    cycles = validate_sources(prior, recent, validation)
    left, right = pair_index(prior, True), pair_index(recent, False)
    if (len(left) != prior['matched_towns'] or
        len(right) != recent['matched_districts']):
        raise ValueError('Administrative town index no longer reconciles')
    common = sorted(set(left) & set(right))
    not_shared_prior = sorted(set(left) - set(right))
    not_shared_recent = sorted(set(right) - set(left))
    if not common:
        raise ValueError('No verifiable three-year towns')
    scores = {}
    for cycle, year in [('2014_to_2018', 2018), ('2018_to_2022', 2022)]:
        obj = cycles[cycle]
        if obj.get('matched_towns') != len(obj.get('towns', [])):
            raise ValueError('Truncated frozen historical score panel')
        idx = {}
        for r in obj['towns']:
            k = (normalize(r['county']), normalize(r['district']))
            if k in idx:
                raise ValueError('Duplicate frozen historical holdout row')
            idx[k] = r
        scores[cycle] = idx
    rows = []
    members = defaultdict(lambda: {'2014_to_2018': [], '2018_to_2022': []})
    counties = defaultdict(lambda: {'matched_towns': 0,
                                    'station_count_changed': 0,
                                    'electorate_change_gt_8pct': 0})
    for c, code, name in common:
        old, new = left[(c, code, name)], right[(c, code, name)]
        y14 = checked_year(old['years']['2014'])
        y18 = checked_year(old['years']['2018'])
        repeated = checked_year(new['years']['2018'])
        y22 = checked_year(new['years']['2022'])
        if y18 != repeated:
            raise ValueError('Independent 2018 CEC counts disagree across source panels: '+c+'/'+name)
        score_key = (c, name)
        if score_key not in scores['2014_to_2018'] or score_key not in scores['2018_to_2022']:
            raise ValueError('Cross-cycle source not present in frozen validation')
        r18, r22 = scores['2014_to_2018'][score_key], scores['2018_to_2022'][score_key]
        check_holdout(r18, 2018, y18, y14)
        check_holdout(r22, 2022, y22, y18)
        changed_stations = len({y14['stations'], y18['stations'], y22['stations']}) > 1
        change14 = y18['electorate']/y14['electorate'] - 1
        change18 = y22['electorate']/y18['electorate'] - 1
        changed_electorate = max(abs(change14), abs(change18)) > .08
        flags = {'station_count_changed': changed_stations,
                 'electorate_change_gt_8pct': changed_electorate}
        cohorts = ['common_towns']
        if not changed_stations:
            cohorts.append('unchanged_station_count')
        if not changed_electorate:
            cohorts.append('electorate_change_within_8pct')
        if not changed_stations and not changed_electorate:
            cohorts.append('both_diagnostic_flags_clear')
        for cohort in cohorts:
            members[(cohort, '2014_to_2018')]['2014_to_2018'].append(r18)
            members[(cohort, '2018_to_2022')]['2018_to_2022'].append(r22)
        stats = counties[c]
        stats['matched_towns'] += 1
        stats['station_count_changed'] += int(changed_stations)
        stats['electorate_change_gt_8pct'] += int(changed_electorate)
        rows.append({'county': c, 'district': name, 'town_code': code,
                     'code_and_name_only': not bool(old.get('documented_name_change')),
                     'documented_name_change': old.get('documented_name_change'),
                     '2018_duplicate_source_counts_identical': True,
                     'year_electorates': {'2014': y14['electorate'],
                                         '2018': y18['electorate'],
                                         '2022': y22['electorate']},
                     'year_station_counts': {'2014': y14['stations'],
                                             '2018': y18['stations'],
                                             '2022': y22['stations']},
                     'electorate_change_2014_to_2018_pct': round(100*change14, 3),
                     'electorate_change_2018_to_2022_pct': round(100*change18, 3),
                     'diagnostic_only_flags': flags})
    group_results = {}
    for cohort in COHORTS:
        group_results[cohort] = {
            '2014_to_2018': score(members[(cohort, '2014_to_2018')]['2014_to_2018'], '2014_to_2018'),
            '2018_to_2022': score(members[(cohort, '2018_to_2022')]['2018_to_2022'], '2018_to_2022')}
    return {'schema_version': 1,
            'kind': 'cec_three_year_common_town_ecological_stability_audit',
            'years': [2014, 2018, 2022],
            'source_files': [
                'turnout-district-panel-2014-2018.json',
                'turnout-district-panel-2018-2022.json',
                'turnout-two-cycle-town-validation.json'],
            'matched_counties': len(counties),
            'matched_towns': len(rows),
            'documented_2015_name_changes_count': sum(bool(x.get('documented_name_change')) for x in rows),
            'prior_two_year_towns': len(left),
            'later_two_year_towns': len(right),
            'unmatched_prior': [{'county': c, 'code': code, 'district': name}
                                for c, code, name in not_shared_prior],
            'unmatched_recent': [{'county': c, 'code': code, 'district': name}
                                 for c, code, name in not_shared_recent],
            '2018_duplicate_source_counts_disagreements': 0,
            'unchanged_station_count_towns': group_results['unchanged_station_count']['2014_to_2018']['n_towns'],
            'electorate_change_gt_8pct_towns': sum(
                x['diagnostic_only_flags']['electorate_change_gt_8pct'] for x in rows),
            'county_diagnostics': [{'county': c, **v} for c, v in sorted(counties.items())],
            'cohorts': group_results, 'towns': rows,
            'time_order': 'Holdout forecasts frozen before test election; realized test-year electorate weights enter scoring only.',
            'post_election_selection_warning': 'Station counts and change in electorate require test-year observations. Diagnostic strata cannot be selected prospectively and cannot demonstrate forecasting gains.',
            'geography_status': 'code_and_original_name_continuity_only_no_historical_boundary_overlay',
            'historical_boundary_reference': 'https://maps.nlsc.gov.tw/pro/013_41_layer.html',
            'no_individual_voter_inference': True,
            'candidate_vote_data_used': False,
            'forecast_2026_modified': False,
            'promotion_gate': {'status': 'blocked', 'formal_hb_tlef_unchanged': True,
                               'allow_2026_candidate_win_probability_modification': False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior', type=Path, default=ROOT/'data/turnout-district-panel-2014-2018.json')
    parser.add_argument('--recent', type=Path, default=ROOT/'data/turnout-district-panel-2018-2022.json')
    parser.add_argument('--holdout', type=Path, default=ROOT/'data/turnout-two-cycle-town-validation.json')
    parser.add_argument('--output', type=Path, default=ROOT/'data/turnout-three-year-compatibility.json')
    args = parser.parse_args()
    data = lambda p: json.loads(p.read_text(encoding='utf-8'))
    result = evaluate(data(args.prior), data(args.recent), data(args.holdout))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                      allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({
        'matched_counties': result['matched_counties'],
        'matched_towns': result['matched_towns'],
        'unchanged_station_count_towns': result['unchanged_station_count_towns'],
        'electorate_change_gt_8pct_towns': result['electorate_change_gt_8pct_towns'],
        'promotion_gate': result['promotion_gate']['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
