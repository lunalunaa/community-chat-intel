"""Cross-tabulation helper for the community chat-history analysis pipeline.

Loads `users.json` (produced by analyze.py) and computes decision-relevant
pivots:

  1. Provider cluster × Location proxy
     → Do mainland users lean on Chinese providers more than overseas?
  2. Messaging platform × Location
     → Does a given IM-platform's demand concentrate in mainland / overseas / both?
  3. Feature depth × Retention
     → Do users who engage with your product's differentiator features retain better?
  4. Install path × Friction
     → Does one install path (e.g. WSL) hit more friction than another?
  5. Impersonator mentions × Friction
     → Are users who referenced impersonator/clone sites more confused?
  6. Competitor usage × Retention
     → Do users who've tried competing products lapse faster?
  7. Acquisition channel × Retention
     → Which acquisition channels produce sticky users?

Output:
  - crosstabs.json : all pivots as nested {row: {col: count}} dicts
  - crosstabs.md   : human-readable markdown tables, ready to paste into report.md §14
  - merges into stats.json as .crosstabs

USAGE:
  python3 crosstabs.py --users-json ./out/users.json --out ./out/crosstabs.json [--stats-path ./out/stats.json]
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ----------------------------------------------------------------------------
# Category definitions — how we collapse per-user counters into pivot axes
# ----------------------------------------------------------------------------

# Provider clusters — aggregate the provider labels into strategic buckets
PROVIDER_CLUSTERS = {
    "chinese_api": {
        "deepseek",
        "kimi_moonshot",
        "qwen_alibaba",
        "glm_zhipu",
        "minimax",
        "volcengine_ark",
        "doubao",
        "baichuan",
        "yi_01ai",
    },
    "western_api": {"anthropic_claude", "openai", "gemini_google"},
    "aggregator_or_portal": {"openrouter", "huggingface", "modelscope"},
    "self_hosted": {"ollama", "vllm", "llamacpp", "lmstudio"},
}

# Messaging platform — collapse to 4 buckets
MESSAGING_BUCKETS = {
    "feishu_lark": {"feishu", "lark_intl"},
    "wechat_family": {"wechat", "wecom"},
    "dingtalk": {"dingtalk"},
    "western_im": {"discord", "telegram", "slack", "signal", "matrix", "whatsapp"},
}

# Deep / differentiator features (vs basic chat use) — EXAMPLE set, matches
# the placeholder labels in keywords.py's PRODUCT_FEATURES. Replace with
# your own product's differentiator feature labels.
DEEP_FEATURES = {"skills", "memory", "cron", "delegate", "mcp", "browser", "vision"}

# Install path buckets
INSTALL_BUCKETS = {
    "wsl": {"wsl"},
    "native_unix": {"linux_native", "macos"},
    "docker": {"docker"},
    "hosted": {"hosted_service"},
    "vps_ssh": {"vps_ssh"},
    # windows_native, uv_python, pip_python are too generic / cross-cutting
}

# Acquisition channels
ACQUISITION_BUCKETS = {
    "social_media": {"twitter_x", "reddit"},
    "tech_community": {"github_trending", "hackernews", "hf_model_page"},
    "content": {"article_link", "video"},
    "word_of_mouth": {"friend_recommendation"},
}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def nonzero(d: dict) -> set:
    """Return set of keys whose value is > 0."""
    return {k for k, v in (d or {}).items() if (v or 0) > 0}


def user_provider_clusters(u: dict) -> set[str]:
    """Which provider clusters has this user mentioned at least once?"""
    mentioned = nonzero(u.get("providers", {}))
    clusters = set()
    for cluster_name, members in PROVIDER_CLUSTERS.items():
        if mentioned & members:
            clusters.add(cluster_name)
    return clusters


def user_messaging_buckets(u: dict) -> set[str]:
    mentioned = nonzero(u.get("messaging", {}))
    buckets = set()
    for name, members in MESSAGING_BUCKETS.items():
        if mentioned & members:
            buckets.add(name)
    return buckets


def user_install_buckets(u: dict) -> set[str]:
    mentioned = nonzero(u.get("install", {}))
    buckets = set()
    for name, members in INSTALL_BUCKETS.items():
        if mentioned & members:
            buckets.add(name)
    return buckets


def user_acquisition_buckets(u: dict) -> set[str]:
    mentioned = nonzero(u.get("acquisition", {}))
    buckets = set()
    for name, members in ACQUISITION_BUCKETS.items():
        if mentioned & members:
            buckets.add(name)
    return buckets


def user_location(u: dict) -> str:
    """Assign user to a timezone-proxy location based on modal posting hour (UTC).

    Mirrors the logic in analyze.py's `tz_buckets` aggregation.
    """
    hod = u.get("hours_of_day", {}) or {}
    if not hod:
        return "unknown"
    # Find modal hour
    modal_h = max(hod.items(), key=lambda kv: kv[1])[0]
    try:
        h = int(modal_h)
    except (TypeError, ValueError):
        return "unknown"
    if 12 <= h <= 16:
        return "mainland_evening"
    if h in (0, 1, 2, 3, 4, 5, 6):
        return "na_evening"
    if 18 <= h <= 22:
        return "eu_evening"
    return "other"


def user_retention(u: dict, now: datetime) -> str:
    """Classify user by last-seen recency."""
    try:
        last = datetime.fromisoformat(u["last_seen"])
    except (KeyError, ValueError):
        return "unknown"
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    delta = now - last
    if delta <= timedelta(days=30):
        return "active_30d"
    if delta <= timedelta(days=90):
        return "lapsed_30_90d"
    return "lapsed_90d_plus"


def user_friction_level(u: dict) -> str:
    """Count distinct friction categories, bucket into none/low/high."""
    count = sum(1 for v in (u.get("friction", {}) or {}).values() if v > 0)
    if count == 0:
        return "none"
    if count <= 2:
        return "low_1_2"
    return "high_3plus"


def user_feature_depth(u: dict) -> str:
    mentioned = nonzero(u.get("features", {}))
    return "deep_features" if (mentioned & DEEP_FEATURES) else "chat_only"


def user_has_impersonator(u: dict) -> str:
    return (
        "yes"
        if any(v > 0 for v in (u.get("impersonator_domains", {}) or {}).values())
        else "no"
    )


def user_has_competitor(u: dict) -> str:
    """Has this user mentioned any competitor product?"""
    competitors = nonzero(u.get("competitors", {}))
    return "yes" if competitors else "no"


# ----------------------------------------------------------------------------
# Pivot builder
# ----------------------------------------------------------------------------


def pivot(
    users: list[dict], row_fn, col_fn, multi_row: bool = False
) -> dict[str, dict[str, int]]:
    """Build a {row: {col: count}} pivot.

    If multi_row=True, row_fn returns a set and user counts in every row it
    matches. Otherwise row_fn returns a single string.
    """
    table: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for u in users:
        col = col_fn(u)
        if multi_row:
            rows = row_fn(u) or {"(none)"}
        else:
            rows = {row_fn(u)}
        for row in rows:
            table[row][col] += 1
    return {r: dict(c) for r, c in table.items()}


def format_table_md(
    title: str,
    table: dict[str, dict[str, int]],
    interpretation: str = "",
    note: str = "",
) -> str:
    """Render a pivot as markdown table with row/col totals and row-wise percentages."""
    if not table:
        return f"### {title}\n\n_No data._\n\n"

    rows = sorted(table.keys())
    cols = sorted({c for row in table.values() for c in row.keys()})

    # Compute totals
    row_totals = {r: sum(table[r].get(c, 0) for c in cols) for r in rows}
    col_totals = {c: sum(table[r].get(c, 0) for r in rows) for c in cols}
    grand_total = sum(row_totals.values())

    lines = [f"### {title}", ""]
    if note:
        lines.append(f"*{note}*")
        lines.append("")

    # Counts table
    lines.append("**Counts:**")
    lines.append("")
    header = "| " + " | ".join([""] + cols + ["**total**"]) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(cols) + 2))
    for r in rows:
        row_vals = [str(table[r].get(c, 0)) for c in cols]
        lines.append(
            "| " + " | ".join([f"**{r}**"] + row_vals + [f"**{row_totals[r]}**"]) + " |"
        )
    total_vals = [str(col_totals[c]) for c in cols]
    lines.append(
        "| " + " | ".join(["**total**"] + total_vals + [f"**{grand_total}**"]) + " |"
    )
    lines.append("")

    # Row-wise percentages (each row sums to 100%)
    if grand_total > 0:
        lines.append(
            "**Row %** (each row sums to 100%; interpret as 'of users in this row, what fraction fall in each col'):"
        )
        lines.append("")
        lines.append(header)
        lines.append("|" + "---|" * (len(cols) + 2))
        for r in rows:
            if row_totals[r] == 0:
                row_vals = ["—" for _ in cols]
            else:
                row_vals = [
                    f"{100 * table[r].get(c, 0) / row_totals[r]:.0f}%" for c in cols
                ]
            lines.append(
                "| "
                + " | ".join([f"**{r}**"] + row_vals + [f"**n={row_totals[r]}**"])
                + " |"
            )
        lines.append("")

    # Sample-size warnings
    small_rows = [r for r in rows if row_totals[r] < 10]
    if small_rows:
        lines.append(
            f"> ⚠️  Small-sample rows (N < 10): {', '.join(small_rows)}. Treat as directional at best."
        )
        lines.append("")

    if interpretation:
        lines.append("**Interpretation hint:** " + interpretation)
        lines.append("")

    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def build_crosstabs(users: list[dict], now: datetime) -> tuple[dict[str, Any], str]:
    """Return (json_dict, markdown_string)."""

    # Restrict to Chinese-speaking cohort: zh_primary + bilingual
    zh_users = [
        u for u in users if u.get("language_primary") in ("zh_primary", "bilingual")
    ]

    md_sections = []
    md_sections.append("# Cross-tabulations — Chinese-speaking cohort")
    md_sections.append("")
    md_sections.append(
        f"**Cohort size:** {len(zh_users)} users (zh_primary + bilingual).  "
    )
    md_sections.append(f"**Reference time:** {now.isoformat()}  ")
    md_sections.append(f"**Total users in dataset:** {len(users)}")
    md_sections.append("")
    md_sections.append(
        "All pivots below use the Chinese cohort only. Small-sample warnings flag rows with N < 10."
    )
    md_sections.append("")
    md_sections.append("---")
    md_sections.append("")

    crosstabs: dict[str, Any] = {
        "metadata": {
            "chinese_cohort_size": len(zh_users),
            "total_users": len(users),
            "reference_time": now.isoformat(),
        },
    }

    # --- 1. Provider cluster × Location -----------------------------------
    t = pivot(zh_users, user_provider_clusters, user_location, multi_row=True)
    crosstabs["provider_cluster_x_location"] = t
    md_sections.append(
        format_table_md(
            "1. Provider cluster × Location proxy",
            t,
            interpretation=(
                "If `chinese_api` is concentrated in `mainland_evening`, "
                "mainland users rely on Chinese providers — "
                "strengthens the case for investing in that provider's UX. "
                "If `western_api` dominates `na_evening` / `eu_evening`, overseas Chinese diaspora "
                "still works via Anthropic/OpenAI and doesn't need mainland-specific provider UX."
            ),
            note="Multi-row: a user mentioning both DeepSeek and Claude counts in both provider-cluster rows.",
        )
    )

    # --- 2. Messaging platform × Location ---------------------------------
    t = pivot(zh_users, user_messaging_buckets, user_location, multi_row=True)
    crosstabs["messaging_x_location"] = t
    md_sections.append(
        format_table_md(
            "2. Messaging platform × Location",
            t,
            interpretation=(
                "Which IM platform does each geography actually care about? "
                "`feishu_lark` concentrated in `mainland_evening` → a Feishu-adapter "
                "investment is mainland-driven. `wechat_family` dominating → pivot toward WeChat instead. "
                "`dingtalk` non-trivial → enterprise-adjacent mainland users; consider a DingTalk adapter."
            ),
            note="Multi-row: a user mentioning both Feishu and WeChat counts in both rows.",
        )
    )

    # --- 3. Feature depth × Retention -------------------------------------
    t = pivot(zh_users, user_feature_depth, lambda u: user_retention(u, now))
    crosstabs["feature_depth_x_retention"] = t
    md_sections.append(
        format_table_md(
            "3. Feature depth × Retention",
            t,
            interpretation=(
                "Do users who engage with your product's differentiator features retain better? "
                "If `deep_features` shows higher `active_30d` share than `chat_only`, "
                "your differentiators ARE sticky — lead marketing and docs with them. "
                "If not, the differentiators aren't landing; simplify onboarding first."
            ),
        )
    )

    # --- 4. Install path × Friction ---------------------------------------
    t = pivot(zh_users, user_install_buckets, user_friction_level, multi_row=True)
    crosstabs["install_x_friction"] = t
    md_sections.append(
        format_table_md(
            "4. Install path × Friction",
            t,
            interpretation=(
                "Which install paths produce the most pain? If `wsl` has a higher "
                "`high_3plus` share than `native_unix`, invest in a Windows-native "
                "or better-documented WSL2 install flow. If `hosted` has near-zero "
                "friction, push more users toward the hosted on-ramp."
            ),
            note="Multi-row: users mentioning multiple install paths count in each.",
        )
    )

    # --- 5. Impersonator mentions × Friction ------------------------------
    t = pivot(zh_users, user_has_impersonator, user_friction_level)
    crosstabs["impersonator_x_friction"] = t
    md_sections.append(
        format_table_md(
            "5. Impersonator mentions × Friction",
            t,
            interpretation=(
                "Do users who referenced an impersonator/clone site report MORE friction? "
                "If yes → the impersonator docs are actively misleading users and driving "
                "support burden. Brand-protection priority escalates. "
                "If no → mentions are casual / curious, not load-bearing."
            ),
        )
    )

    # --- 6. Competitor usage × Retention -----------------------------------
    t = pivot(zh_users, user_has_competitor, lambda u: user_retention(u, now))
    crosstabs["competitor_x_retention"] = t
    md_sections.append(
        format_table_md(
            "6. Competitor usage × Retention",
            t,
            interpretation=(
                "Do users who've tried a competing product lapse faster, or do they use "
                "your product alongside it? Higher `lapsed_90d_plus` for `yes` → users are "
                "migrating away to competitors. Higher `active_30d` for `yes` → users "
                "dual-wield; you aren't losing to competitors, you're complementary."
            ),
        )
    )

    # --- 7. Acquisition channel × Retention -------------------------------
    t = pivot(
        zh_users,
        user_acquisition_buckets,
        lambda u: user_retention(u, now),
        multi_row=True,
    )
    crosstabs["acquisition_x_retention"] = t
    md_sections.append(
        format_table_md(
            "7. Acquisition channel × Retention",
            t,
            interpretation=(
                "Which acquisition sources produce sticky Chinese users? "
                "Higher `active_30d` share for `tech_community` vs `content` → "
                "invest in GitHub / HN / HF model-card presence over long-form articles. "
                "Higher `active_30d` for `word_of_mouth` → community referral is the strongest driver; "
                "invest in community-lead relationships, not broad-reach content."
            ),
            note="Multi-row: users mentioning multiple acquisition signals count in each.",
        )
    )

    md_sections.append("---")
    md_sections.append("")
    md_sections.append(
        "*Generated by `crosstabs.py`. See `plan.md §3` for the methodology behind "
        "each pivot's row/column collapse logic. To add new pivots, edit the "
        "`build_crosstabs()` function in `crosstabs.py`.*"
    )

    return crosstabs, "\n".join(md_sections)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Cross-tabulation helper for community chat analysis."
    )
    p.add_argument(
        "--users-json",
        required=True,
        type=Path,
        help="Path to users.json produced by analyze.py",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("./out/crosstabs.json"),
        help="Output path for crosstabs.json (default: ./out/crosstabs.json)",
    )
    p.add_argument(
        "--stats-path",
        type=Path,
        default=None,
        help="Path to stats.json to merge .crosstabs into (default: <out dir>/stats.json)",
    )
    p.add_argument(
        "--reference-time",
        type=str,
        default=None,
        help="ISO timestamp to use as 'now' for retention calc (default: latest last_seen in data)",
    )
    args = p.parse_args()

    if not args.users_json.exists():
        print(
            f"[error] {args.users_json} not found. Run analyze.py first.",
            file=sys.stderr,
        )
        return 2

    users_data = json.loads(args.users_json.read_text(encoding="utf-8"))
    # users.json is dict {user_id: user_obj}; convert to list
    users = (
        list(users_data.values()) if isinstance(users_data, dict) else list(users_data)
    )
    print(f"[load] {len(users)} users from {args.users_json}", file=sys.stderr)

    # Determine reference time for retention
    if args.reference_time:
        now = datetime.fromisoformat(args.reference_time)
    else:
        last_seens = []
        for u in users:
            try:
                last_seens.append(datetime.fromisoformat(u["last_seen"]))
            except (KeyError, ValueError):
                pass
        if last_seens:
            now = max(last_seens)
        else:
            now = datetime.now(tz=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    crosstabs, md = build_crosstabs(users, now)

    # Write JSON
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(crosstabs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[write] {args.out}", file=sys.stderr)

    # Write markdown
    md_path = args.out.with_suffix(".md")
    md_path.write_text(md, encoding="utf-8")
    print(f"[write] {md_path}", file=sys.stderr)

    # Merge into stats.json if present
    stats_path = args.stats_path or (args.out.parent / "stats.json")
    if stats_path.exists():
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        stats["crosstabs"] = crosstabs
        stats_path.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[merge] updated {stats_path} with .crosstabs section", file=sys.stderr)

    print(f"[done] {len(crosstabs) - 1} pivots computed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
