#!/usr/bin/env python3

import argparse
import json
import sys
from crex_score import ScoreFetchError, extract_match_key, fetch_score_sync, format_score_text


def validate_match(value: str) -> str:
    try:
        return extract_match_key(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog="scorecli",
        description="Fetch CREX live cricket score from a match key or CREX URL",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  scorecli 127D
  scorecli 127D --json
  scorecli https://crex.com/cricket-live-score/ck-vs-gg-3rd-match-lanka-premier-league-2026-match-updates-127D
        """,
    )

    parser.add_argument(
        "match",
        type=validate_match,
        help="CREX match key or full CREX match URL",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--json",
        action="store_true",
        help="show JSON output",
    )
    group.add_argument(
        "--text",
        action="store_true",
        help="show text output",
    )

    return parser.parse_args()


def run():
    args = parse_arguments()

    try:
        data = fetch_score_sync(args.match)
    except ScoreFetchError as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": exc.status_code,
                    "message": exc.message,
                },
                indent=2,
            )
        )
        sys.exit(1)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    print(format_score_text(data))


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
