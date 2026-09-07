"""Extract the inherited data and evaluate historical baselines without future leakage."""
import hashlib
import json
import math
from pathlib import Path

VERSION = '2026.09-research.1'


def historical_prediction(history, target, method):
    years = sorted(y for y in history if int(y) < target)
    if not years:
        raise ValueError('No pre-election observations')
    if method == 'last':
        weights = [int(y == years[-1]) for y in years]
    else:
        weights = list(range(1, len(years) + 1))
    return {p: sum(history[y]['shares'].get(p, 0) * w for y, w in zip(years, weights)) / sum(weights)
            for p in ('KMT', 'DPP')}


def evaluate(counties):
    rows = []
    for target in (2018, 2022):
        for method in ('last', 'ensemble'):
            errors, details = [], []
            for name, county in counties.items():
                h = county['history']['local']
                if str(target) not in h or not any(int(y) < target for y in h):
                    continue
                pred = historical_prediction(h, target, method)
                for party in ('KMT', 'DPP'):
                    actual = h[str(target)]['shares'].get(party, 0)
                    error = actual - pred[party]
                    errors.append(error)
                    details.append({'county': name, 'party': party, 'predicted': round(pred[party], 2),
                                    'actual': actual, 'error': round(error, 2)})
            rows.append({'year': target, 'method': method, 'n': len(errors),
                         'training_years': [y for y in (2014, 2018) if y < target],
                         'mae': sum(abs(e) for e in errors) / len(errors),
                         'rmse': math.sqrt(sum(e * e for e in errors) / len(errors)), 'details': details})
    return rows


def prepare(root: Path, now):
    source = (root / 'site/base.html').read_text(encoding='utf-8')
    app, _ = json.JSONDecoder().raw_decode(source.split('const APP =', 1)[1].lstrip())
    config = json.loads((root / 'config.json').read_text(encoding='utf-8'))
    counties = []
    for name in app['order']:
        c = app['counties'][name]
        f = c['forecast']
        counties.append({'name': name, 'region': c['region'], 'history': c['history'],
                         'baseline': [f['blue_exp'], f['dpp_exp'], f['third_exp']],
                         'baseline_candidates': [f.get('blue_candidate'), f.get('dpp_candidate')],
                         'candidate_warning': f.get('candidate_match_warning'),
                         'features': c['features']})
    fingerprint = hashlib.sha256(json.dumps(counties, sort_keys=True).encode()).hexdigest()[:16]
    return {'schema_version': 1, 'model_version': VERSION, 'generated_at': now.isoformat(),
            'baseline_date': config['baseline_cutoff'], 'fingerprint': fingerprint,
            'counties': counties, 'validation': evaluate(app['counties']),
            'assumptions': {'prior_sd': 0.42, 'national_sd': 0.16, 'regional_sd': 0.10,
                            'future_variance_per_day': 0.00035, 'house_sd': 0.14,
                            'design_effect': 2, 'half_life_days': 45,
                            'simulations': 6000, 'seed': 20260907},
            'scope': 'Inherited June scenario means, not independently verified 2026 candidate predictions. Other is a consolidated hypothetical candidate. Historical party-share evaluation does not calibrate these probabilities.'}
