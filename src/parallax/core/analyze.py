"""Community chat-history analysis pipeline.

Reads a platform-native chat export (Discord JSON, Telegram JSON, Slack
export, Lark/Feishu output, generic CSV, or a pre-normalized canonical JSON),
produces:
  - stats.json : aggregated statistics ready for report insertion
  - users.json : per-user profiles (hashed ids)
  - report.md  : report-template.md with stats placeholders filled in

Works for any target-language / region community. Pick a target language and
region with ``--target-language`` / ``--region`` (see ``languages.py`` for the
full list, or add your own language/region profile there). Defaults to no
language classification (every message counts as "target") and the "global"
region profile — pass ``--target-language zh`` (or any registered code) to
enable the target/other/mixed cohort split.

This module is a thin backward-compatibility shim. The adapter implementations
and the canonical :class:`Message` live in :mod:`parallax.core.adapters`, and
the analysis pipeline (``run_pipeline``, ``render_report``, ``merge_stats``,
``ensure_salt``, classification and extraction helpers) lives in
:mod:`parallax.core.pipeline`. Everything is re-exported here so existing
``from parallax.core import analyze`` and ``from parallax.core.analyze import X``
imports keep working unchanged.

USAGE:
    parallax-analyze \\
        --input path/to/export.json \\
        --platform discord \\
        --out ./out/ \\
        [--target-language ja] \\
        [--region jp] \\
        [--template ./report-template.md] \\
        [--salt-file ./user_hash_salt.key] \\
        [--channels "#general,#help"] \\
        [--since 2025-10-01] \\
        [--until 2026-04-22] \\
        [--verbose]

The pipeline stages:
  1. Load adapter (platform-specific → canonical schema)
  2. Language classify each message (per --target-language profile)
  3. Build per-user profiles
  4. Keyword extraction (providers, competitors, messaging, features, friction, shadow, acquisition)
  5. Question detection (per --target-language patterns) + reply-graph for help-answered-rate
  6. Retention cohort assignment
  7. Aggregate stats
  8. Write outputs

LLM topic tagging (optional) is a separate script — not in the MVP pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from parallax.core import languages as lang
from parallax.core.adapters import (
    ADAPTERS,
    Message,
    _hash_id,
    _parse_ts,
    load_canonical,
    load_csv_export,
    load_discord_export,
    load_lark_export,
    load_slack_export,
    load_telegram_export,
)
from parallax.core.pipeline import (
    UserProfile,
    _max_ts,
    _merge_counters,
    _min_ts,
    classify_language,
    classify_url,
    ensure_salt,
    extract_urls,
    is_question,
    merge_stats,
    render_report,
    run_pipeline,
)

__all__ = [
    "ADAPTERS",
    "Message",
    "UserProfile",
    "_hash_id",
    "_max_ts",
    "_merge_counters",
    "_min_ts",
    "_parse_ts",
    "classify_language",
    "classify_url",
    "ensure_salt",
    "extract_urls",
    "is_question",
    "load_canonical",
    "load_csv_export",
    "load_discord_export",
    "load_lark_export",
    "load_slack_export",
    "load_telegram_export",
    "main",
    "merge_stats",
    "render_report",
    "run_pipeline",
]


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Community chat-history analysis pipeline."
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="Path to chat export JSON"
    )
    parser.add_argument("--platform", required=True, choices=list(ADAPTERS.keys()))
    parser.add_argument(
        "--out", type=Path, default=Path("./out"), help="Output directory"
    )
    parser.add_argument(
        "--target-language",
        type=str,
        default="none",
        help="Language code to treat as the 'target' cohort for classification "
        "(see languages.py LANGUAGE_PROFILES for the full list: zh, ja, ko, "
        "ru, ar, he, th, vi, es, fr, de, pt, id, ...). "
        "Pass 'none' (default) to disable language classification entirely — every "
        "message counts as target (useful for already-monolingual exports). "
        "Set to a language code to enable the target/other/mixed cohort split.",
    )
    parser.add_argument(
        "--region",
        type=str,
        default="global",
        help="Region code controlling external-community platforms and the "
        "timezone-proxy location buckets (see languages.py REGION_PROFILES: "
        "cn, jp, kr, ru, latam, mena, global, ...). Unknown codes fall back "
        "to 'global'. Default: global.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).parent.parent / "templates" / "report-template.md",
        help="Report template with {{stats.xxx}} placeholders "
        "(default: the bundled parallax/templates/report-template.md)",
    )
    parser.add_argument(
        "--salt-file",
        type=Path,
        default=Path("./user_hash_salt.key"),
        help="User-ID hashing salt file, auto-generated on first run if missing "
        "(default: ./user_hash_salt.key in the current working directory — "
        "never commit this file)",
    )
    parser.add_argument(
        "--channels",
        type=str,
        default=None,
        help="Comma-separated channel names to include",
    )
    parser.add_argument(
        "--since", type=str, default=None, help="ISO date inclusive lower bound"
    )
    parser.add_argument(
        "--until", type=str, default=None, help="ISO date inclusive upper bound"
    )
    parser.add_argument(
        "--keep-names",
        action="store_true",
        help="Keep display names in users.json (default: redacted)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="Channel label override (lark adapter only; used when the export doesn't carry chat_name)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        help="Output format for stats. json (default) writes stats.json. csv writes "
        "stats.csv with a flat key-value layout suitable for spreadsheet/BI tools. "
        "Both formats are always written alongside users.json and report.md.",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only process new messages since last run. Requires an existing "
        "stats.json in the output directory; merges new results into it. "
        "Uses a SQLite state store (parallax_state.db in the output dir).",
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    language_profile = lang.get_language_profile(args.target_language)
    if args.target_language not in (None, "none", "off") and language_profile is None:
        print(
            f"[warn] unknown --target-language '{args.target_language}'; "
            f"known codes: {', '.join(sorted(lang.LANGUAGE_PROFILES))}. "
            f"Falling back to no language classification.",
            file=sys.stderr,
        )
    region_profile = lang.get_region_profile(args.region)
    if args.region not in lang.REGION_PROFILES:
        print(
            f"[warn] unknown --region '{args.region}'; "
            f"known codes: {', '.join(sorted(lang.REGION_PROFILES))}. "
            f"Falling back to 'global'.",
            file=sys.stderr,
        )

    salt = ensure_salt(args.salt_file)
    adapter = ADAPTERS[args.platform]
    # Lark adapter accepts an optional `channel` kwarg; others don't.
    if args.platform == "lark":
        messages = list(adapter(args.input, salt, channel=args.channel))
    else:
        messages = list(adapter(args.input, salt))

    # Incremental mode: filter to only new messages
    existing_stats = None
    if args.incremental:
        from parallax.core.state import StateStore

        state_db = args.out / "parallax_state.db"
        stats_path = args.out / "stats.json"
        if not stats_path.exists():
            print(
                "[warn] --incremental requires an existing stats.json in the output dir; "
                "running full analysis instead.",
                file=sys.stderr,
            )
        else:
            with StateStore(state_db) as store:
                new_messages = store.filter_new(messages, str(args.input))
                if args.verbose:
                    print(
                        f"[incremental] {len(new_messages)} new / {len(messages)} total messages",
                        file=sys.stderr,
                    )
                if not new_messages:
                    print(
                        "[incremental] no new messages; nothing to do.", file=sys.stderr
                    )
                    return 0
                existing_stats = json.loads(stats_path.read_text())
                messages = new_messages

    if args.verbose:
        print(
            f"[load] {len(messages)} messages from {args.platform} export",
            file=sys.stderr,
        )
        print(
            f"[config] target_language={args.target_language} region={args.region}",
            file=sys.stderr,
        )

    channels_filter = (
        {c.strip() for c in args.channels.split(",")} if args.channels else None
    )
    since = (
        datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        if args.since
        else None
    )
    until = (
        datetime.fromisoformat(args.until).replace(tzinfo=timezone.utc)
        if args.until
        else None
    )

    users, stats = run_pipeline(
        messages,
        channels_filter=channels_filter,
        since=since,
        until=until,
        verbose=args.verbose,
        language_profile=language_profile,
        region_profile=region_profile,
    )

    # Incremental mode: merge new stats into existing, mark messages as seen
    if existing_stats is not None:
        stats = merge_stats(existing_stats, stats)
        from parallax.core.state import StateStore

        state_db = args.out / "parallax_state.db"
        with StateStore(state_db) as store:
            store.mark_seen(messages, str(args.input))
        if args.verbose:
            print(
                "[incremental] merged stats and marked messages as seen",
                file=sys.stderr,
            )

    # Write stats.json
    stats_path = args.out / "stats.json"
    stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[write] {stats_path}", file=sys.stderr)

    # Write stats.csv (flat key-value layout for BI tools)
    if args.format == "csv":
        import csv

        csv_path = args.out / "stats.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["category", "key", "value"])
            for category, data in stats.items():
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, (int, float, str)):
                            writer.writerow([category, key, value])
                        elif isinstance(value, dict):
                            for subkey, subvalue in value.items():
                                if isinstance(subvalue, (int, float, str)):
                                    writer.writerow(
                                        [category, f"{key}.{subkey}", subvalue]
                                    )
                        elif isinstance(value, list):
                            writer.writerow(
                                [category, key, ",".join(str(v) for v in value)]
                            )
                else:
                    writer.writerow(["root", category, str(data)])
        print(f"[write] {csv_path}", file=sys.stderr)

    # Write users.json (redacted by default)
    users_serializable = {}
    for uid, u in users.items():
        d = asdict(u)
        d["channels"] = sorted(u.channels)
        d["hours_of_day"] = dict(u.hours_of_day)
        for key in (
            "providers",
            "competitors",
            "messaging",
            "features",
            "install",
            "friction",
            "shadow_community",
            "acquisition",
            "impersonator_domains",
            "official_domains",
        ):
            d[key] = dict(getattr(u, key))
        d["first_seen"] = u.first_seen.isoformat()
        d["last_seen"] = u.last_seen.isoformat()
        d["language_primary"] = u.language_primary()
        if not args.keep_names:
            d["display_name"] = "<redacted>"
        users_serializable[uid] = d
    users_path = args.out / "users.json"
    users_path.write_text(
        json.dumps(users_serializable, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[write] {users_path}", file=sys.stderr)

    # Write report
    if args.template.exists():
        report_md = render_report(args.template, stats)
        report_path = args.out / "report.md"
        report_path.write_text(report_md, encoding="utf-8")
        print(f"[write] {report_path}", file=sys.stderr)
    else:
        print(
            f"[warn] template not found at {args.template}; skipping report rendering",
            file=sys.stderr,
        )

    print("[done] Analysis complete.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
