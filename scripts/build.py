"""Build a self-contained Pages artifact; never upload the source workspace."""
import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
try:
    from research_model import prepare
except ModuleNotFoundError:
    from scripts.research_model import prepare

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def paused(config, now):
    return datetime.fromisoformat(config['publication_pause_start']) <= now < datetime.fromisoformat(config['publication_pause_end'])


def build(now=None):
    now = now or datetime.now(timezone.utc)
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    feed_path = ROOT / 'data/polls.json'
    feed = json.loads(feed_path.read_text(encoding='utf-8'))
    if feed.get('schema_version') != 1 or not isinstance(feed.get('records'), list):
        raise ValueError('Invalid poll archive; refusing to replace public site')
    dist = ROOT / 'dist'
    if dist.exists():
        assert dist.resolve().parent == ROOT.resolve() and dist.name == 'dist'
        shutil.rmtree(dist)
    dist.mkdir()
    (dist / '.nojekyll').touch()
    if paused(config, now):
        (dist / 'index.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>選舉資料暫停公開</title><main style="max-width:640px;margin:15vh auto;padding:24px;font-family:system-ui"><h1>選舉資料暫停公開</h1><p>選前暫停發布民調及相關預測。投票結束後恢復。</p><a href="https://www.cec.gov.tw/">中央選舉委員會</a></main></html>', encoding='utf-8')
        print('Built paused publication: no forecast assets or polls in artifact')
        return
    source = (ROOT / 'site/base.html').read_text(encoding='utf-8')
    start = source.index('async function loadExternalPolls(manual=false){')
    end = source.index('function clearExternalPolls(){', start)
    source = source[:start] + 'async function loadExternalPolls(){return window.PublicPolls?.reload() ?? 0;}\n' + source[end:]
    source = source.replace("const LS_KEY = 'tw2026_admin_map_updates_v2';", "const LS_KEY = 'tw2026_public_private_scenarios_v1';")
    source = source.replace('  initApiPanel();', '  /* Public build has no browser-side API credentials. */')
    source = source.replace('tw2026_admin_map_api_config_v2', 'tw2026_public_api_disabled_v1')
    source = source.replace("if(!cfg.enabled)", "if(true)")
    source = re.sub(r'<title>.*?</title>', '<title>2026 台灣選舉預測 | 自動民調追蹤</title>', source, count=1)
    security = '<meta name="referrer" content="strict-origin-when-cross-origin">\n<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'self\' \'unsafe-inline\'; style-src \'self\' \'unsafe-inline\'; img-src \'self\' data: blob:; connect-src \'self\' https://zh.wikipedia.org https://cdn.jsdelivr.net https://raw.githubusercontent.com; font-src \'self\'; object-src \'none\'; base-uri \'self\'; form-action \'none\'">\n'
    source = source.replace('<head>', '<head>\n' + security, 1)
    source = source.replace('</head>', '<link rel="stylesheet" href="public-polls.css">\n</head>', 1)
    public_feed = {k: v for k, v in feed.items() if k != 'reports'}
    public_feed['schedule_hours'] = config['schedule_hours']
    public_feed['stale_after_hours'] = config['stale_after_hours']
    public_feed['publication_pause_start'] = config['publication_pause_start']
    public_feed['publication_pause_end'] = config['publication_pause_end']
    payload = json.dumps(public_feed, ensure_ascii=False).replace('<', '\\u003c')
    source = source.replace('</body>', '<script type="application/json" id="publicPollBootstrap">' + payload + '</script>\n<script src="public-polls.js"></script>\n</body>')
    if re.search(r'(?:sk-ant-api\w*-|ghp_|github_pat_)[A-Za-z0-9_\-]{20,}', source):
        raise ValueError('Potential credential in source; refusing public build')
    source = source.replace('</head>', '<style>.legacy-notice{position:relative;z-index:999;padding:12px 24px;background:#fff3df;color:#714416;font:14px system-ui}.legacy-notice a{color:#174fa8}</style></head>', 1)
    source = re.sub(r'(<body[^>]*>)', r'\1<div class="legacy-notice">舊版進階工作台：沿用舊模型與既有情境，與研究版推估不同步。<a href="index.html">返回新版</a></div>', source, count=1)
    (dist / 'legacy.html').write_text(source, encoding='utf-8')
    for name in (
        'index.html', 'styles.css', 'gis-edition.css', 'forecast-command-center.css', 'race-center.css', 'source-v52.css', 'poll-source-v52.mjs',
        'governance-v56.css', 'governance-v56.mjs',
        'forecast.mjs', 'charts.mjs', 'app.mjs',
        'candidate-research.mjs', 'candidate-app.mjs', 'candidate-engine.mjs',
        'history-atlas.css', 'history-atlas.mjs',
        'historical-polls-ui.mjs', 'evidence-ui.mjs', 'scenario-rules.mjs',
         'market-observatory.mjs', 'market-observatory.css',
         'market-fusion.mjs',
         'market-joint-shadow.mjs',
         'turnout-sensitivity.mjs', 'turnout-ui.mjs', 'turnout.css',
         'precinct-turnout-ui.mjs',
         'turnout-district-panel.mjs', 'turnout-association-ui.mjs', 'turnout-shadow-ui.mjs',
        'scenario-studio.mjs', 'motion.css', 'motion.mjs', 'motion-v2.css',
        'motion-v2.mjs', 'motion-v3.css', 'motion-v3.mjs', 'motion-v4.css',
        'motion-v4.mjs'
    ):
        shutil.copy2(ROOT / 'site' / name, dist / name)
    for name in ('history-atlas.css', 'history-atlas.mjs'):
        if not (dist / name).is_file():
            raise ValueError(f'Missing required History Atlas asset: {name}')
    old_index = (ROOT / 'site/index.html').read_text(encoding='utf-8').replace('src="candidate-app.mjs"', 'src="app.mjs"')
    old_index = re.sub(r'\s*<a[^>]*data-view="updates"[^>]*>.*?</a>', '', old_index)
    (dist / 'research-legacy.html').write_text(old_index, encoding='utf-8')
    model_data = prepare(ROOT, now)
    from model.data import digest, load_dataset
    from model.roster import load_roster
    from model.pipeline import run
    historical = load_dataset(ROOT / 'data/candidate-history.json')
    roster = load_roster(ROOT / 'data/registration-roster-2026.json', historical)
    research = run(historical, now.isoformat())
    research.pop('experimental_registration_forecast', None)
    research['registration_roster'] = {'candidate_count': roster['candidate_count'],
                                     'county_count': roster['county_count'], 'as_of': roster['as_of']}
    for gate in research['release']['gates']:
        if gate['id'] == 'registered_roster_import':
            gate.update(passed=True, reason='Registered entrants imported; final qualification pending.')
    research['artifact_hash'] = digest({k: v for k, v in research.items() if k != 'artifact_hash'})
    model_data['candidate_research'] = research
    model_data['registration_roster'] = roster
    (dist / 'candidate-research.json').write_text(json.dumps(research, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    model_data['feed_checked_at'] = feed['checked_at']
    model_data['publication_pause_start'] = config['publication_pause_start']
    model_data['publication_pause_end'] = config['publication_pause_end']
    (dist / 'model-data.json').write_text(json.dumps(model_data, ensure_ascii=False), encoding='utf-8')
    (dist / 'polls.json').write_text(json.dumps(public_feed, ensure_ascii=False, indent=2), encoding='utf-8')
    markets_path = ROOT / 'data/market-snapshots.json'
    markets = json.loads(markets_path.read_text(encoding='utf-8')) if markets_path.exists() else {'schema_version':1,'status':'unavailable','events':[],'history':[]}
    if markets.get('schema_version') != 1 or not isinstance(markets.get('events'), list):
        raise ValueError('Invalid market snapshot archive')
    (dist / 'market-snapshots.json').write_text(json.dumps(markets, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

    # The CEC station source is distributed as county/year chunks.
    # Do not invent station rows when the official download is unavailable.
    booth_source = ROOT / 'data/cec-precincts'
    if (booth_source / 'index.json').exists():
        booth_index = json.loads((booth_source / 'index.json').read_text(encoding='utf-8'))
        if booth_index.get('schema_version') != 1 or len(booth_index.get('entries', [])) != 66:
            raise ValueError('Unverified or incomplete CEC polling-station archive')
        for entry in booth_index['entries']:
            if entry.get('status') == 'official_precinct_aggregate_verified':
                station_file = booth_source / Path(entry['path']).name
                if not station_file.is_file():
                    raise ValueError('CEC station data chunk missing: '+str(station_file))
        shutil.copytree(booth_source, dist / 'cec-precincts')

    district_panel_path = ROOT / 'data/turnout-district-panel-2018-2022.json'
    if district_panel_path.exists():
        district_panel = json.loads(district_panel_path.read_text(encoding='utf-8'))
        if (district_panel.get('schema_version') != 1 or
            district_panel.get('kind') != 'observed_turnout_district_panel_not_an_individual_turnout_model' or
            not district_panel.get('official_forecast_unchanged') or
            len(district_panel.get('counties', [])) != 22):
            raise ValueError('Unverified cross-election township turnout panel')
        (dist / 'turnout-district-panel-2018-2022.json').write_text(
            json.dumps(district_panel, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

    research_outputs = (
        ('cec-town-candidate-association-2018-2022.json',
         'historical_ecological_candidate_turnout_association_only',
         'official_forecast_unchanged'),
        ('turnout-holdout-2018-2022.json',
         'cec_historical_time_ordered_turnout_holdout',
         'official_2026_forecast_unchanged'),
    )
    for name, expected_kind, guard in research_outputs:
        path = ROOT / 'data' / name
        if path.is_file():
            source = json.loads(path.read_text(encoding='utf8'))
            if (source.get('schema_version') != 1 or source.get('kind') != expected_kind or
                source.get(guard) is not True or len(source.get('counties', [])) not in (0, 22) and
                source.get('kind') == 'historical_ecological_candidate_turnout_association_only'):
                raise ValueError('Candidate vote / turnout backtest data failed quality gate')
            (dist / name).write_text(
                json.dumps(source, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')

    shadow_path = ROOT / 'data/turnout-shadow-ablation-2022.json'
    if shadow_path.exists():
        shadow = json.loads(shadow_path.read_text(encoding='utf8'))
        gate = shadow.get('promotion_gate', {})
        if (shadow.get('schema_version') != 1 or
            shadow.get('kind') != 'turnout_forecast_shadow_ablation_2022_exploratory' or
            shadow.get('training_cutoff_election') != 2018 or
            shadow.get('holdout_election') != 2022 or
            not shadow.get('uses_2022_outcomes_only_for_scoring') or
            shadow.get('candidate_party_votes_used_in_predictors') is not False or
            gate.get('status') != 'blocked' or
            gate.get('allow_2026_candidate_win_probability_modification') is not False):
            raise ValueError('Unverified exploratory turnout-shadow model gate')
        (dist / 'turnout-shadow-ablation-2022.json').write_text(
            json.dumps(shadow, ensure_ascii=False, indent=2, allow_nan=False),
            encoding='utf8')

    turnout_path = ROOT / 'data/turnout-history-2018-2022.json'
    turnout = json.loads(turnout_path.read_text(encoding='utf-8'))
    if turnout.get('schema_version') != 1 or len(turnout.get('records', [])) != 22:
        raise ValueError('Unverified historical turnout source: refusing to publish')
    for year in ('2018', '2022'):
        eligible = sum(c['years'][year]['eligible'] for c in turnout['records'])
        cast = sum(c['years'][year]['cast'] for c in turnout['records'])
        if (eligible, cast) != (turnout['national'][year]['eligible'],
                                turnout['national'][year]['cast']):
            raise ValueError('Historical turnout national total mismatch')
    (dist / 'turnout-history-2018-2022.json').write_text(
        json.dumps(turnout, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

    from model.v5_product import build_product
    product = build_product(ROOT, now, feed)
    product['publication_pause_start'] = config['publication_pause_start']
    product['publication_pause_end'] = config['publication_pause_end']
    product['fingerprint'] = digest({k:v for k,v in product.items() if k != 'fingerprint'})
    (dist / 'candidate-model.json').write_text(json.dumps(product, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    current_research = {'schema_version':1, 'model_version':product['model_version'],
        'model_fingerprint':product['fingerprint'],
        'historical_polling':{**product['historical_polling'], 'records':json.loads((ROOT/'data/historical-polls-tvbs.json').read_text(encoding='utf-8'))['records']},
        'data_hash':product['training_data_hash'], 'audit':product['training']['audit'],
        'backtest':product['validation']['fundamentals'], 'training':product['training'],
        'v4_validation':product.get('v4_validation'),
        'v5_validation':product['v5_validation'],
        'fragmentation_gate':product['fragmentation_gate'],
        'surveys':json.loads((ROOT/'data/survey-source-audit.json').read_text(encoding='utf-8'))}
    (dist / 'candidate-validation.json').write_text(json.dumps(current_research, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    shutil.copy2(ROOT/'data/candidate-history-cec.json', dist/'candidate-history-cec.json')
    shutil.copy2(ROOT/'data/historical-polls-tvbs.json', dist/'historical-polls-tvbs.json')
    shutil.copy2(ROOT/'data/forecast-history.json', dist/'forecast-history.json')
    shutil.copy2(ROOT/'model/releases/v5.0-public-beta.1.json', dist/'v5.0-public-beta.1.json')
    shutil.copy2(ROOT/'docs/MODEL_CARD_V5_PUBLIC_BETA.md', dist/'MODEL_CARD_V5_PUBLIC_BETA.md')
    # Preserve the previous public-beta governance artifacts for version comparison.
    shutil.copy2(ROOT/'model/releases/v4.1-public-beta.2.json', dist/'v4.1-public-beta.2.json')
    shutil.copy2(ROOT/'docs/MODEL_CARD_V4_1_PUBLIC_BETA.md', dist/'MODEL_CARD_V4_1_PUBLIC_BETA.md')
    for name in ('public-polls.js', 'public-polls.css'):
        shutil.copy2(ROOT / 'site' / name, dist / name)
    shutil.copytree(ROOT / 'site/gis', dist / 'gis', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'site/vendor', dist / 'vendor', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'THIRD_PARTY.md', dist / 'THIRD_PARTY.md')
    print('Built dist/index.html:', product['model_version'], ';', len(feed['records']),
          'archived questions;', product['diagnostics']['included_reports'], 'candidate-model inputs;',
          product['diagnostics']['structural_mode_counts'], 'fragmentation gates;',
          product['fragmentation_gate']['triggered_count'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--at', help='ISO timestamp for publication-gate tests')
    args = parser.parse_args()
    build(datetime.fromisoformat(args.at) if args.at else None)
