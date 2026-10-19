"""Cross-platform CLI: uv run python scripts/build_pack.py --limit 20."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from feibi_pack.builder import build  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index", type=Path, help="Local Phoebe-Hub JSON; default fetches upstream"
    )
    parser.add_argument("--output", type=Path, default=Path("build/pack"))
    parser.add_argument("--cache", type=Path, default=Path(".cache/feibi"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--refresh", action="store_true", help="Revalidate cached URLs with ETag/Last-Modified"
    )
    parser.add_argument(
        "--include-review", action="store_true", help="Include uncertain images in review category"
    )
    parser.add_argument("--overrides", type=Path, help="Human decisions keyed by content SHA-256")
    parser.add_argument(
        "--skip-failed",
        action="store_true",
        help="Record unavailable/invalid images and continue; default is strict",
    )
    parser.add_argument(
        "--complete-name-captions",
        action="store_true",
        help="Accept explicit name-based captions as done; does not claim visual review",
    )
    parser.add_argument("--version", default="0.1.0")
    args = vars(parser.parse_args())
    if args["overrides"]:
        args["overrides"] = json.loads(args["overrides"].read_text("utf-8"))
    result = build(**args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["usable_images"]:
        print("No usable images exported; inspect review_queue.json.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
