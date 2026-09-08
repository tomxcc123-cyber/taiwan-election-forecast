"""One-time, explicit import. Normal training never reads UI HTML."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.data import import_legacy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "site/base.html")
    parser.add_argument("--output", type=Path, default=ROOT / "data/candidate-history.json")
    args = parser.parse_args()
    data = import_legacy(args.source)
    # A later data correction requires a new explicit output, never an accidental overwrite.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(data["data_hash"])
