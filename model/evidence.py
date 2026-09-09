"""Read-only evidence layer. Neither news nor evidence grades alter simulated votes."""
import json
from datetime import date, datetime, timezone, timedelta
from urllib.parse import urlparse
from .data import digest


def compact_snapshot(product):
    return {"generated_at": product["generated_at"], "fingerprint": product["fingerprint"],
            "model_version": product["model_version"],
            "inputs": {key: product.get(key) for key in
                       ("feed_hash", "candidate_set_version", "training_data_hash", "historical_poll_hash", "context_hash")},
            "poll_ids": sorted(a["id"] for a in product["poll_audit"] if a["included"]),
            "counties": [{"name": r["name"], "race_id": r["race_id"],
                          "candidates": [{k: c[k] for k in
                                          ("candidate_id", "name", "mean", "probability")}
                                         for c in r["candidates"]]} for r in product["counties"]]}


def retain_snapshots(snapshots):
    # Keep each model version's final snapshot per Taipei calendar day.
    unique = {}
    for s in snapshots:
        stamp = datetime.fromisoformat(s['generated_at'])
        if stamp.tzinfo is None:
            raise ValueError('Snapshot requires timezone')
        if len(s['counties']) != 22:
            raise ValueError('Incomplete snapshot')
        key = (stamp.astimezone(timezone(timedelta(hours=8))).date().isoformat(), s['model_version'])
        if key not in unique or stamp > datetime.fromisoformat(unique[key]['generated_at']):
            unique[key] = s
    return sorted(unique.values(), key=lambda s: datetime.fromisoformat(s['generated_at']))[-180:]


def attach_evidence(product, feed, root):
    context = json.loads((root/'data/candidate-context.json').read_text(encoding='utf-8'))
    today = datetime.fromisoformat(product['generated_at']).astimezone(timezone(timedelta(hours=8))).date()
    events = []
    for e in context['events']:
        if urlparse(e['source_url']).scheme != 'https' or e['model_status'] != 'not_estimated':
            raise ValueError('Invalid context evidence')
        if date.fromisoformat(e['date']) > today or date.fromisoformat(context['reviewed_at']) > today:
            continue
        race = next((r for r in product['counties'] if r['name'] == e['county']), None)
        if race is None or not any(c['name'] == e['candidate'] for c in race['candidates']):
            raise ValueError('Context evidence does not match roster')
        events.append(e)
    included = {a['id'] for a in product['poll_audit'] if a['included']}
    accepted = [r for r in feed['records'] if r['id'] in included]
    product['context_hash'] = digest(context)
    product['evidence'] = {'reviewed_at': context['reviewed_at'], 'coverage': context['coverage'], 'events': events,
        'grading_rule': 'A：60天內至少兩家機構的配對民調；B：至少一家；C：無近期配對民調；D：已核對但尚未建模的跨黨支持缺項。等級衡量資料，不是準確率。'}
    product['poll_counts'] = {
        'reports': len({r['source_url'] for r in feed['records']}),
        'questions': len(feed['records']), 'included_questions': len(accepted),
        'covered_counties': len({r['county'] for r in accepted}),
        'roster_exclusions': sum(not a['included'] and '民調人選與登記名單不符' in a['reason'] for a in product['poll_audit']),
        'latest_eligible_fieldwork': max((r['date'] for r in accepted), default=None)}
    for r in product['counties']:
        polls = [p for p in accepted if p['county'] == r['name']]
        recent = [p for p in polls if 0 <= (today-date.fromisoformat(p['date'])).days <= 60]
        sources = {p.get('pollster_id') or p['source'] for p in recent}
        local_evidence = [e['id'] for e in events if e['county'] == r['name']]
        applied = set(product.get('support_model', {}).get('applied_evidence', []))
        risks = [eid for eid in local_evidence if eid not in applied]
        grade = 'D' if risks else 'A' if len(sources) >= 2 else 'B' if sources else 'C'
        r['quality']['evidence'] = {'grade': grade, 'recent_questions': len(recent),
            'support_proxy_evidence': [eid for eid in local_evidence if eid in applied],
            'recent_pollsters': len(sources), 'unmodeled_evidence': risks,
            'reason': '已知跨黨支持尚未建模' if risks else
                      '近期有多機構配對民調' if grade == 'A' else
                      '近期僅一機構配對民調' if grade == 'B' else
                      '無60天內配對民調；較早民調仍依模型規則納入' if polls else '無直接配對民調'}
    archive_path = root/'data/forecast-history.json'
    snapshots = json.loads(archive_path.read_text(encoding='utf-8'))['snapshots'] if archive_path.exists() else []
    snapshots = [s for s in retain_snapshots(snapshots)
                 if datetime.fromisoformat(s['generated_at']) < datetime.fromisoformat(product['generated_at'])]
    product['tracking'] = {'schema_version': 1, 'snapshots': snapshots,
        'notice': '存檔是實際建置的基準摘要，不含使用者情境。尚未保存的日期不補造；輸入變更紀錄不是因果貢獻分解。'}
