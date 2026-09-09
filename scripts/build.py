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
    # Only the build-owned output directory can be cleared, including paused builds.
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
    # The cloud feed replaces the legacy file importer, retaining manual/private scenarios.
    start = source.index('async function loadExternalPolls(manual=false){')
    end = source.index('function clearExternalPolls(){', start)
    source = source[:start] + 'async function loadExternalPolls(){return window.PublicPolls?.reload() ?? 0;}\n' + source[end:]
    source = source.replace("const LS_KEY = 'tw2026_admin_map_updates_v2';", "const LS_KEY = 'tw2026_public_private_scenarios_v1';")
    source = source.replace('  initApiPanel();', '  /* Public build has no browser-side API credentials. */')
    source = source.replace('tw2026_admin_map_api_config_v2', 'tw2026_public_api_disabled_v1')
    # Keep the local assistant, but disallow the inherited paid API pathway in public build.
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
    # Retain the original advanced workspace at a separate route, not hidden in the new DOM.
    source = source.replace('</head>', '<style>.legacy-notice{position:relative;z-index:999;padding:12px 24px;background:#fff3df;color:#714416;font:14px system-ui}.legacy-notice a{color:#174fa8}</style></head>', 1)
    source = re.sub(r'(<body[^>]*>)', r'\1<div class="legacy-notice">舊版進階工作台：沿用舊模型與既有情境，與研究版推估不同步。<a href="index.html">返回新版</a></div>', source, count=1)
    (dist / 'legacy.html').write_text(source, encoding='utf-8')
    for name in ('index.html', 'styles.css', 'forecast.mjs', 'charts.mjs', 'app.mjs', 'candidate-research.mjs', 'candidate-app.mjs', 'candidate-engine.mjs', 'historical-polls-ui.mjs', 'evidence-ui.mjs', 'scenario-rules.mjs', 'scenario-studio.mjs'):
        shutil.copy2(ROOT / 'site' / name, dist / name)
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
    # Only historical validation is public. Experimental 2026 candidate probabilities stay offline.
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
    from model.product import build_product
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
        'surveys':json.loads((ROOT/'data/survey-source-audit.json').read_text(encoding='utf-8'))}
    (dist / 'candidate-validation.json').write_text(json.dumps(current_research, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    shutil.copy2(ROOT/'data/candidate-history-cec.json', dist/'candidate-history-cec.json')
    shutil.copy2(ROOT/'data/historical-polls-tvbs.json', dist/'historical-polls-tvbs.json')
    for name in ('public-polls.js', 'public-polls.css'):
        shutil.copy2(ROOT / 'site' / name, dist / name)
    shutil.copytree(ROOT / 'site/vendor', dist / 'vendor')
    shutil.copy2(ROOT / 'THIRD_PARTY.md', dist / 'THIRD_PARTY.md')
    print('Built dist/index.html:', product['model_version'], ';', len(feed['records']),
          'archived questions;', product['diagnostics']['included_reports'], 'candidate-model inputs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--at', help='ISO timestamp for publication-gate tests')
    args = parser.parse_args()
    build(datetime.fromisoformat(args.at) if args.at else None)
