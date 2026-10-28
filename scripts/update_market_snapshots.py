"""Read-only research snapshots of verified Taiwan local-election prediction markets.

Gamma public GET only. No trading, wallets, credentials, order submission, or
inference-model ingestion. Source errors keep prior observations marked stale.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'data/market-registry-2026.json'
OUTPUT = ROOT / 'data/market-snapshots.json'
API = 'https://gamma-api.polymarket.com/events'
EVENT_PATH = 'https://polymarket.com/event/'


def finite(value, default=None):
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return v if math.isfinite(v) else default


def bounded(value, lower=0, upper=1):
    v = finite(value)
    return v if v is not None and lower <= v <= upper else None


def parse_array(value):
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return None


def fetch(slug):
    if not re.fullmatch(r'[a-z0-9-]{8,150}', slug):
        raise ValueError('Unsafe market slug')
    url = API + '?' + urllib.parse.urlencode({'slug': slug})
    req = urllib.request.Request(url, headers={'User-Agent': 'TaiwanElectionResearch/1.0 (public read-only academic data)', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=18) as response:
        if urllib.parse.urlparse(response.geturl()).hostname != 'gamma-api.polymarket.com':
            raise ValueError('Untrusted market API redirect')
        raw = response.read(1400001)
    if len(raw) > 1400000:
        raise ValueError('Market API payload too large')
    return json.loads(raw)


def normalize_event(payload, spec, retrieved_at):
    if not isinstance(payload, list) or len(payload) != 1:
        raise ValueError('Expected one matching event')
    event = payload[0]
    slug = spec['slug']
    if event.get('slug') != slug or not isinstance(event.get('markets'), list):
        raise ValueError('Event slug or markets mismatch')
    if not event.get('title') or not event.get('description'):
        raise ValueError('Missing event title or rules')
    description = event['description']
    if 'November 28, 2026' not in description or 'Taiwan' not in description:
        raise ValueError('Event rules are not verified for the 2026 Taiwan election')
    if not event.get('active') or event.get('closed'):
        raise ValueError('Event inactive or closed')
    outcomes = []
    for market in event['markets']:
        if not market.get('active') or market.get('closed'):
            continue
        name = market.get('groupItemTitle')
        choices = parse_array(market.get('outcomes'))
        prices = parse_array(market.get('outcomePrices'))
        if not isinstance(name, str) or not 1 <= len(name) <= 90:
            continue
        if not isinstance(choices, list) or not isinstance(prices, list) or len(choices) != len(prices) or 'Yes' not in choices:
            continue
        price = bounded(prices[choices.index('Yes')])
        if price is None:
            continue
        bid = bounded(market.get('bestBid'))
        ask = bounded(market.get('bestAsk'))
        spread = round(ask - bid, 5) if bid is not None and ask is not None and ask >= bid else None
        outcomes.append({
            'name': name, 'market_id': str(market.get('id') or ''),
            'probability': round(price, 5),
            'best_bid': bid, 'best_ask': ask, 'spread': spread,
            'volume_usd': finite(market.get('volumeNum', market.get('volume')), 0),
            'liquidity_usd': finite(market.get('liquidityNum', market.get('liquidity')), 0),
        })
    if not outcomes:
        raise ValueError('No validated Yes outcome prices')
    liquidity = finite(event.get('liquidity'), 0)
    volume = finite(event.get('volume'), 0)
    if min(volume, liquidity) < 0:
        raise ValueError('Invalid market-wide volume or liquidity')
    outcomes.sort(key=lambda x: x['probability'], reverse=True)
    return {
        'county': spec['county'], 'slug': slug, 'event_id': str(event.get('id') or ''),
        'title': event['title'][:150], 'source_url': EVENT_PATH + slug,
        'quote_as_of': str(event.get('updatedAt') or retrieved_at),
        'retrieved_at': retrieved_at, 'stale': False,
        'volume_usd': volume, 'volume24h_usd': finite(event.get('volume24hr'), 0),
        'liquidity_usd': liquidity,
        'outcomes': outcomes,
        'data_quality': 'thin' if volume < 10000 or liquidity < 10000 else 'unverified_market_price',
        'caution': 'Market Yes share price is not a calibrated election probability or polling share.',
    }


def build_snapshot(registry, previous, getter=fetch, now=None):
    stamp = now or datetime.now(timezone.utc).isoformat(timespec='seconds')
    specs = registry.get('events')
    if registry.get('schema_version') != 1 or not isinstance(specs, list):
        raise ValueError('Invalid market registry')
    if len({e.get('slug') for e in specs}) != len(specs):
        raise ValueError('Duplicate event registry slugs')
    old = {x['slug']: x for x in previous.get('events', [])}
    events, errors, history = [], [], list(previous.get('history', []))
    for spec in specs:
        slug = spec['slug']
        try:
            candidate = normalize_event(getter(slug), spec, stamp)
            events.append(candidate)
            for row in candidate['outcomes']:
                key = f"{slug}|{row['market_id']}"
                if (not history or not any(x.get('key') == key and x.get('checked_at') == stamp for x in history)):
                    history.append({'key': key, 'slug': slug, 'county': spec['county'], 'name': row['name'],
                                    'checked_at': stamp, 'probability': row['probability']})
        except (OSError, ValueError, TypeError, KeyError, TimeoutError) as exc:
            errors.append({'slug': slug, 'county': spec['county'], 'reason': str(exc)[:140]})
            if slug in old:
                events.append({**old[slug], 'stale': True})
    events.sort(key=lambda x: (x.get('county', ''), x.get('slug', '')))
    # Retain at most 90 points per tracked market contract, with no inferred prices.
    by_key = {}
    for item in history:
        key = item.get('key')
        if isinstance(key, str) and bounded(item.get('probability')) is not None:
            by_key.setdefault(key, []).append(item)
    bounded_history = [p for points in by_key.values() for p in points[-90:]]
    bounded_history.sort(key=lambda x: (x['checked_at'], x['key']))
    return {
        'schema_version': 1, 'source': 'Polymarket Gamma public read-only API',
        'checked_at': stamp,
        'status': 'ok' if not errors else ('degraded' if events else 'unavailable'),
        'registry_count': len(specs), 'events': events, 'errors': errors,
        'history': bounded_history,
        'research_only': True, 'used_in_forecast': False,
        'notice': 'Market prices, poll percentages and model win probabilities are separate quantities. Prices may be distorted by liquidity, spreads, fees, selection and contract rules.',
    }


def write_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as temp:
        json.dump(value, temp, ensure_ascii=False, indent=2, allow_nan=False)
        temp.write('\n')
        name = temp.name
    os.replace(name, path)


def main():
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    previous = json.loads(OUTPUT.read_text(encoding='utf-8')) if OUTPUT.exists() else {}
    output = build_snapshot(registry, previous)
    write_atomic(OUTPUT, output)
    print(f"Market snapshots: valid {sum(not e['stale'] for e in output['events'])}, "
          f"stale {sum(e['stale'] for e in output['events'])}, "
          f"errors {len(output['errors'])}, history {len(output['history'])}")


if __name__ == '__main__':
    main()
