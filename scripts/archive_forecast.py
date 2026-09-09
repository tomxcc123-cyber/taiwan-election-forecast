"""Persist a compact, genuine build snapshot; no fabricated historical predictions."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.evidence import compact_snapshot, retain_snapshots


def archive(model_path, archive_path):
    if not model_path.exists():
        print('No forecast artifact; snapshot skipped (publication pause).')
        return
    product = json.loads(model_path.read_text(encoding='utf-8'))
    snapshots = json.loads(archive_path.read_text(encoding='utf-8'))['snapshots'] if archive_path.exists() else []
    snapshots = retain_snapshots([*snapshots, compact_snapshot(product)])
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(json.dumps({'schema_version': 1, 'snapshots': snapshots}, ensure_ascii=False,
                                     allow_nan=False, indent=2), encoding='utf-8')
    print(f'Archived {len(snapshots)} genuine forecast summaries')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=ROOT/'dist/candidate-model.json')
    parser.add_argument('--archive', type=Path, default=ROOT/'data/forecast-history.json')
    args = parser.parse_args()
    archive(args.model, args.archive)
