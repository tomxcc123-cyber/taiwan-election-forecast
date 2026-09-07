"""Build a self-contained Pages artifact; never upload the source workspace."""
import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    (dist / 'index.html').write_text(source, encoding='utf-8')
    (dist / 'polls.json').write_text(json.dumps(public_feed, ensure_ascii=False, indent=2), encoding='utf-8')
    for name in ('public-polls.js', 'public-polls.css'):
        shutil.copy2(ROOT / 'site' / name, dist / name)
    shutil.copytree(ROOT / 'site/vendor', dist / 'vendor')
    shutil.copy2(ROOT / 'THIRD_PARTY.md', dist / 'THIRD_PARTY.md')
    print('Built dist/index.html:', len(feed['records']), 'poll questions;', len(feed['polls']), 'new model inputs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--at', help='ISO timestamp for publication-gate tests')
    args = parser.parse_args()
    build(datetime.fromisoformat(args.at) if args.at else None)
