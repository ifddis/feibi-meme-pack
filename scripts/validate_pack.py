"""Validate official schemas, image bytes, paths and semantic identities."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from feibi_pack.validation import validate_pack  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate_pack(args.pack, args.require_complete), ensure_ascii=False, indent=2))
