#!/usr/bin/env python3
"""Compare two stats.json files and highlight what changed.

Usage:
    parallax-diff --old ./run1/stats.json --new ./run2/stats.json
    parallax-diff --old ./run1/stats.json --new ./run2/stats.json --json

Outputs a human-readable diff showing:
- KPI changes (messages, users, questions, friction, answered rate)
- Counter changes (providers, competitors, features, friction signals, etc.)
- New and disappeared items in each category
- Percentage deltas where meaningful
"""

import argparse
import json
import sys
from pathlib import Path


def _pct(old: float, new: float) -> str:
    if old == 0:
        return "new" if new > 0 else "—"
    pct = ((new - old) / old) * 100
    if pct == 0:
        return "—"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.0f}%"


def _delta_str(old: int, new: int) -> str:
    d = new - old
    if d == 0:
        return "—"
    sign = "+" if d > 0 else ""
    return f"{sign}{d}"


def diff_counter(old: dict, new: dict, label: str) -> list[str]:
    """Diff two counter dicts, return lines of output."""
    lines = []
    all_keys = sorted(set(old) | set(new), key=lambda k: -(new.get(k, 0)))
    changed = False
    for k in all_keys:
        o = old.get(k, 0)
        n = new.get(k, 0)
        if o == n:
            continue
        if not changed:
            lines.append(f"  {label}:")
            changed = True
        status = "new" if o == 0 else "gone" if n == 0 else "changed"
        lines.append(
            f"    {k}: {o} → {n} ({_delta_str(o, n)}, {_pct(float(o), float(n))}) [{status}]"
        )
    return lines


def diff_stats(old: dict, new: dict) -> str:
    """Produce a human-readable diff of two stats dicts."""
    lines = ["=" * 60, "Parallax Stats Diff", "=" * 60, ""]

    old_meta = old.get("metadata", {})
    new_meta = new.get("metadata", {})

    # Date ranges
    old_range = old_meta.get("date_range", ["?", "?"])
    new_range = new_meta.get("date_range", ["?", "?"])
    lines.append(
        f"Period: {old_range[0][:10] if old_range[0] else '?'} → {new_range[0][:10] if new_range[0] else '?'}"
    )
    lines.append("")

    # KPIs
    lines.append("--- KPIs ---")
    old_msgs = old_meta.get("total_messages", 0)
    new_msgs = new_meta.get("total_messages", 0)
    lines.append(
        f"  Messages:      {old_msgs:>6} → {new_msgs:>6} ({_delta_str(old_msgs, new_msgs)}, {_pct(float(old_msgs), float(new_msgs))})"
    )

    old_users = old.get("users", {}).get("total", 0)
    new_users = new.get("users", {}).get("total", 0)
    lines.append(
        f"  Users:         {old_users:>6} → {new_users:>6} ({_delta_str(old_users, new_users)})"
    )

    old_q = old.get("help_answered", {}).get("total_questions", 0)
    new_q = new.get("help_answered", {}).get("total_questions", 0)
    lines.append(
        f"  Questions:     {old_q:>6} → {new_q:>6} ({_delta_str(old_q, new_q)})"
    )

    old_f = sum(old.get("friction_signals", {}).values())
    new_f = sum(new.get("friction_signals", {}).values())
    lines.append(
        f"  Friction:      {old_f:>6} → {new_f:>6} ({_delta_str(old_f, new_f)})"
    )

    old_rate = old.get("help_answered", {}).get("target_answered_rate", 0)
    new_rate = new.get("help_answered", {}).get("target_answered_rate", 0)
    lines.append(f"  Answered rate: {old_rate * 100:>5.0f}% → {new_rate * 100:>5.0f}%")
    lines.append("")

    # Counters
    lines.append("--- Counter changes ---")
    counter_fields = [
        ("providers", "Providers"),
        ("competitors", "Competitors"),
        ("messaging_platforms", "Messaging platforms"),
        ("features", "Features"),
        ("friction_signals", "Friction signals"),
        ("install_paths", "Install paths"),
        ("shadow_community_mentions", "Shadow communities"),
        ("language_distribution", "Language distribution"),
        ("location_proxy", "Location proxy"),
    ]
    for field, label in counter_fields:
        lines.extend(
            diff_counter(
                old.get(field, {}),
                new.get(field, {}),
                label,
            )
        )

    # URL categories
    old_urls = old.get("urls", {}).get("category_counts", {})
    new_urls = new.get("urls", {}).get("category_counts", {})
    lines.extend(diff_counter(old_urls, new_urls, "URL categories"))

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def diff_stats_json(old: dict, new: dict) -> dict:
    """Produce a machine-readable diff of two stats dicts."""
    result = {"kpi": {}, "counters": {}}

    old_meta = old.get("metadata", {})
    new_meta = new.get("metadata", {})

    result["kpi"]["messages"] = {
        "old": old_meta.get("total_messages", 0),
        "new": new_meta.get("total_messages", 0),
    }
    result["kpi"]["users"] = {
        "old": old.get("users", {}).get("total", 0),
        "new": new.get("users", {}).get("total", 0),
    }
    result["kpi"]["questions"] = {
        "old": old.get("help_answered", {}).get("total_questions", 0),
        "new": new.get("help_answered", {}).get("total_questions", 0),
    }

    counter_fields = [
        "providers",
        "competitors",
        "messaging_platforms",
        "features",
        "friction_signals",
        "install_paths",
        "shadow_community_mentions",
        "language_distribution",
        "location_proxy",
    ]
    for field in counter_fields:
        old_c = old.get(field, {})
        new_c = new.get(field, {})
        changes = {}
        for k in set(old_c) | set(new_c):
            o = old_c.get(k, 0)
            n = new_c.get(k, 0)
            if o != n:
                changes[k] = {"old": o, "new": n}
        if changes:
            result["counters"][field] = changes

    return result


def diff_stats_csv(old: dict, new: dict) -> str:
    """Produce a CSV diff of two stats dicts."""
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["category", "key", "old", "new", "delta", "status"])

    old_meta = old.get("metadata", {})
    new_meta = new.get("metadata", {})

    # KPIs
    kpis = [
        (
            "messages",
            old_meta.get("total_messages", 0),
            new_meta.get("total_messages", 0),
        ),
        (
            "users",
            old.get("users", {}).get("total", 0),
            new.get("users", {}).get("total", 0),
        ),
        (
            "questions",
            old.get("help_answered", {}).get("total_questions", 0),
            new.get("help_answered", {}).get("total_questions", 0),
        ),
        (
            "friction",
            sum(old.get("friction_signals", {}).values()),
            sum(new.get("friction_signals", {}).values()),
        ),
    ]
    for key, o, n in kpis:
        if o != n:
            status = "new" if o == 0 else "gone" if n == 0 else "changed"
            writer.writerow(["kpi", key, o, n, n - o, status])

    # Counters
    counter_fields = [
        "providers",
        "competitors",
        "messaging_platforms",
        "features",
        "friction_signals",
        "install_paths",
        "shadow_community_mentions",
        "language_distribution",
        "location_proxy",
    ]
    for field in counter_fields:
        old_c = old.get(field, {})
        new_c = new.get(field, {})
        for k in sorted(set(old_c) | set(new_c)):
            o = old_c.get(k, 0)
            n = new_c.get(k, 0)
            if o != n:
                status = "new" if o == 0 else "gone" if n == 0 else "changed"
                writer.writerow([field, k, o, n, n - o, status])

    # URL categories
    old_urls = old.get("urls", {}).get("category_counts", {})
    new_urls = new.get("urls", {}).get("category_counts", {})
    for k in sorted(set(old_urls) | set(new_urls)):
        o = old_urls.get(k, 0)
        n = new_urls.get(k, 0)
        if o != n:
            status = "new" if o == 0 else "gone" if n == 0 else "changed"
            writer.writerow(["urls", k, o, n, n - o, status])

    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare two stats.json files and highlight what changed."
    )
    parser.add_argument(
        "--old", required=True, type=Path, help="Path to old stats.json"
    )
    parser.add_argument(
        "--new", required=True, type=Path, help="Path to new stats.json"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output JSON instead of text"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    old = json.loads(args.old.read_text())
    new = json.loads(args.new.read_text())

    if args.format == "csv" or args.json:
        if args.format == "csv":
            print(diff_stats_csv(old, new), end="")
        else:
            print(json.dumps(diff_stats_json(old, new), indent=2))
    else:
        print(diff_stats(old, new))
    return 0


if __name__ == "__main__":
    sys.exit(main())
