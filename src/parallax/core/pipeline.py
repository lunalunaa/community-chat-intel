"""Analysis pipeline: classification, extraction, aggregation, and reporting.

This module contains the core analysis stages that run over a list of
canonical :class:`~parallax.core.adapters.Message` instances:

  - language classification (``classify_language``)
  - per-user profiling (``UserProfile``, ``run_pipeline``)
  - URL / question extraction (``extract_urls``, ``classify_url``, ``is_question``)
  - report rendering (``render_report``)
  - salt management (``ensure_salt``)
  - incremental stats merging (``merge_stats``)

The platform adapters and the canonical :class:`Message` dataclass live in
:mod:`parallax.core.adapters`; this module imports them from there.
"""

from __future__ import annotations

import collections
import json
import re
import secrets
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from parallax.core import keywords as kw
from parallax.core import languages as lang
from parallax.core.adapters import ADAPTERS, Message, _hash_id, _parse_ts

# Re-export ``_parse_ts`` so historical callers that reached for it via this
# module (and via the ``analyze`` shim that re-exports from here) keep working.
__all__ = [
    "ADAPTERS",
    "Message",
    "UserProfile",
    "classify_language",
    "classify_url",
    "ensure_salt",
    "extract_urls",
    "is_question",
    "merge_stats",
    "render_report",
    "run_pipeline",
    "_hash_id",
    "_max_ts",
    "_merge_counters",
    "_min_ts",
    "_parse_ts",
]


# ----------------------------------------------------------------------------
# Stage 2 — language classification
# ----------------------------------------------------------------------------


def classify_language(text: str, language_profile: lang.LanguageProfile | None) -> str:
    """Return one of: 'target', 'other', 'mixed', 'unknown'.

    `language_profile=None` means language classification is disabled (every
    non-empty message counts as 'target') — use `--target-language none` for
    already-monolingual exports where the language-cohort split isn't useful.

    Otherwise delegates to `languages.classify_language()`, which generalizes
    the original CJK-ratio heuristic to any registered language profile
    (script-ratio detection for CJK/Cyrillic/Arabic/etc., stopword-ratio for
    Latin-script languages).
    """
    if language_profile is None:
        return "unknown" if not text.strip() else "target"
    result = lang.classify_language(text, language_profile)
    # languages.classify_language() returns 'target'/'mixed'/'other'/'unknown'
    # directly — no translation needed, kept as a thin wrapper for backward
    # compatibility with the old classify_language(text, threshold) signature
    # some callers may still expect a single-text-arg call.
    return result


# ----------------------------------------------------------------------------
# Stage 3 — per-user profiles
# ----------------------------------------------------------------------------


@dataclass
class UserProfile:
    user_id: str  # hashed
    display_name: str
    first_seen: datetime
    last_seen: datetime
    message_count: int = 0
    target_lang_count: int = 0
    mixed_count: int = 0
    other_lang_count: int = 0
    hours_of_day: collections.Counter = field(default_factory=collections.Counter)
    channels: set[str] = field(default_factory=set)
    # Keyword hits
    providers: collections.Counter = field(default_factory=collections.Counter)
    competitors: collections.Counter = field(default_factory=collections.Counter)
    messaging: collections.Counter = field(default_factory=collections.Counter)
    features: collections.Counter = field(default_factory=collections.Counter)
    install: collections.Counter = field(default_factory=collections.Counter)
    friction: collections.Counter = field(default_factory=collections.Counter)
    shadow_community: collections.Counter = field(default_factory=collections.Counter)
    acquisition: collections.Counter = field(default_factory=collections.Counter)
    impersonator_domains: collections.Counter = field(
        default_factory=collections.Counter
    )
    official_domains: collections.Counter = field(default_factory=collections.Counter)
    urls_posted: int = 0
    questions_asked: int = 0
    replies_given: int = 0

    def language_primary(self) -> str:
        """Primary language classification for this user.

        Returns one of: 'silent', 'target_primary', 'other_primary', 'bilingual'.
        ('target_primary'/'other_primary' replace the old 'zh_primary'/
        'en_primary' labels — generalized to any target language, not just
        in the profile's language. 'silent' means the user posted nothing usable to classify.)
        """
        if self.message_count == 0:
            return "silent"
        total = self.target_lang_count + self.mixed_count + self.other_lang_count
        if total == 0:
            return "silent"
        target_pct = (self.target_lang_count + 0.5 * self.mixed_count) / total
        other_pct = (self.other_lang_count + 0.5 * self.mixed_count) / total
        if target_pct >= 0.7:
            return "target_primary"
        if other_pct >= 0.7:
            return "other_primary"
        return "bilingual"


# ----------------------------------------------------------------------------
# Stage 4/5 — extraction
# ----------------------------------------------------------------------------


def extract_urls(text: str) -> list[str]:
    return kw.URL_PATTERN.findall(text)


def classify_url(url: str) -> tuple[str, str]:
    """Return (category, domain). Categories: official, impersonator, hf, modelscope,
    regional_vendor, messaging, other. Domain lists loaded from config."""
    from parallax.core.config import load_url_domains

    url_l = url.lower()
    domain = re.sub(r"^https?://", "", url_l).split("/")[0]
    for d in kw.IMPERSONATOR_DOMAINS:
        if d in url_l:
            return ("impersonator", domain)
    for d in kw.OFFICIAL_DOMAINS:
        if d in url_l:
            return ("official", domain)

    url_cfg = load_url_domains()
    for category, domains in url_cfg.items():
        if category in ("hf", "modelscope", "regional_vendor", "messaging"):
            for d in domains:
                if d in domain:
                    return (category, domain)
    return ("other", domain)


def is_question(text: str, question_pattern: re.Pattern) -> bool:
    return bool(question_pattern.search(text))


def _min_ts(msgs: list[Message]) -> str | None:
    if not msgs:
        return None
    return min(m.timestamp for m in msgs).isoformat()


def _max_ts(msgs: list[Message]) -> str | None:
    if not msgs:
        return None
    return max(m.timestamp for m in msgs).isoformat()


# ----------------------------------------------------------------------------
# Main pipeline
# ----------------------------------------------------------------------------


def run_pipeline(
    messages: list[Message],
    channels_filter: set[str] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    verbose: bool = False,
    language_profile: lang.LanguageProfile | None = None,
    region_profile: lang.RegionProfile | None = None,
) -> tuple[dict[str, UserProfile], dict[str, Any]]:
    """Run the full analysis pipeline.

    `language_profile=None` disables language classification (every message
    counts as target-language; useful for already-monolingual exports).
    `region_profile=None` falls back to the "global" region profile (English-
    default shadow-community platforms + generic timezone buckets).
    """
    region_profile = region_profile or lang.get_region_profile("global")
    shadow_compiled = kw.compile_keyword_dict(region_profile.shadow_community)
    question_pattern = kw.question_pattern_for(
        language_profile.code if language_profile else None
    )

    users: dict[str, UserProfile] = {}
    lang_counts = collections.Counter()
    channel_counts = collections.Counter()
    channel_target_counts = collections.Counter()
    provider_counts = collections.Counter()
    competitor_counts = collections.Counter()
    messaging_counts = collections.Counter()
    feature_counts = collections.Counter()
    install_counts = collections.Counter()
    friction_counts = collections.Counter()
    shadow_counts = collections.Counter()
    acquisition_counts = collections.Counter()
    impersonator_domain_counts = collections.Counter()
    official_domain_counts = collections.Counter()
    url_category_counts = collections.Counter()
    url_domain_counts = collections.Counter()
    question_count = 0
    target_question_count = 0
    target_question_answered = 0

    # For help-answered-rate: build message_id → reply children
    reply_children: dict[str, list[Message]] = collections.defaultdict(list)
    messages_by_id: dict[str, Message] = {}

    # First pass — assemble + filter
    filtered: list[Message] = []
    for m in messages:
        if channels_filter and m.channel not in channels_filter:
            continue
        if since and m.timestamp < since:
            continue
        if until and m.timestamp > until:
            continue
        filtered.append(m)

    if verbose:
        print(f"[pipeline] {len(filtered)} messages after filters", file=sys.stderr)

    # Build reply graph + messages-by-id while processing
    for m in filtered:
        messages_by_id[m.message_id] = m
        if m.reply_to_message_id:
            reply_children[m.reply_to_message_id].append(m)

    # Second pass — per-message extraction
    for m in filtered:
        channel_counts[m.channel] += 1
        msg_lang = classify_language(m.content, language_profile)
        lang_counts[msg_lang] += 1
        if msg_lang in ("target", "mixed"):
            channel_target_counts[m.channel] += 1

        # User profile
        user = users.get(m.author_id)
        if user is None:
            user = UserProfile(
                user_id=m.author_id,
                display_name=m.author_name,
                first_seen=m.timestamp,
                last_seen=m.timestamp,
            )
            users[m.author_id] = user
        user.first_seen = min(user.first_seen, m.timestamp)
        user.last_seen = max(user.last_seen, m.timestamp)
        user.message_count += 1
        user.hours_of_day[m.timestamp.hour] += 1
        user.channels.add(m.channel)
        if msg_lang == "target":
            user.target_lang_count += 1
        elif msg_lang == "mixed":
            user.mixed_count += 1
        elif msg_lang == "other":
            user.other_lang_count += 1

        # Replies
        if m.reply_to_message_id:
            user.replies_given += 1

        # Keyword extraction
        content = m.content or ""
        for label in kw.match_any(content, kw.PROVIDERS_COMPILED):
            user.providers[label] += 1
            provider_counts[label] += 1
        for label in kw.match_any(content, kw.COMPETITORS_COMPILED):
            user.competitors[label] += 1
            competitor_counts[label] += 1
        for label in kw.match_any(content, kw.MESSAGING_COMPILED):
            user.messaging[label] += 1
            messaging_counts[label] += 1
        for label in kw.match_any(content, kw.PRODUCT_FEATURES_COMPILED):
            user.features[label] += 1
            feature_counts[label] += 1
        for label in kw.match_any(content, kw.INSTALL_COMPILED):
            user.install[label] += 1
            install_counts[label] += 1
        for label in kw.match_any(content, kw.FRICTION_COMPILED):
            user.friction[label] += 1
            friction_counts[label] += 1
        for label in kw.match_any(content, shadow_compiled):
            user.shadow_community[label] += 1
            shadow_counts[label] += 1
        for label in kw.match_any(content, kw.ACQUISITION_COMPILED):
            user.acquisition[label] += 1
            acquisition_counts[label] += 1

        # URLs
        for url in extract_urls(content):
            user.urls_posted += 1
            category, domain = classify_url(url)
            url_category_counts[category] += 1
            url_domain_counts[domain] += 1
            if category == "impersonator":
                user.impersonator_domains[domain] += 1
                impersonator_domain_counts[domain] += 1
            elif category == "official":
                user.official_domains[domain] += 1
                official_domain_counts[domain] += 1

        # Also scan raw content for impersonator domain mentions (bare, not URLs)
        content_lower = content.lower()
        for imp_domain in kw.IMPERSONATOR_DOMAINS:
            if imp_domain in content_lower:
                user.impersonator_domains[imp_domain] += 1
                impersonator_domain_counts[imp_domain] += 1

        # Questions
        if is_question(content, question_pattern):
            question_count += 1
            user.questions_asked += 1
            if msg_lang in ("target", "mixed"):
                target_question_count += 1
                # Answered if any reply within 48h
                children = reply_children.get(m.message_id, [])
                for child in children:
                    if (child.timestamp - m.timestamp) <= timedelta(hours=48):
                        target_question_answered += 1
                        break

    # Aggregate stats object
    target_users = [
        u
        for u in users.values()
        if u.language_primary() in ("target_primary", "bilingual")
    ]
    target_primary_users = [
        u for u in users.values() if u.language_primary() == "target_primary"
    ]

    # Retention cohorts
    now = max((m.timestamp for m in filtered), default=datetime.now(tz=timezone.utc))
    active_cutoff = now - timedelta(days=30)
    lapsed_cutoff = now - timedelta(days=90)
    active = [u for u in target_users if u.last_seen >= active_cutoff]
    recently_lapsed = [
        u for u in target_users if active_cutoff > u.last_seen >= lapsed_cutoff
    ]
    long_lapsed = [u for u in target_users if u.last_seen < lapsed_cutoff]
    one_time = [u for u in target_users if u.message_count == 1]

    # Location proxy — modal hour of posting per user (UTC), bucketed per the
    # active region profile's timezone_buckets (see languages.py).
    def modal_hour(u: UserProfile) -> int | None:
        if not u.hours_of_day:
            return None
        return u.hours_of_day.most_common(1)[0][0]

    def bucket_hour(h: int) -> str:
        for label, (lo, hi) in region_profile.timezone_buckets.items():
            if lo <= hi:
                if lo <= h <= hi:
                    return label
            else:
                # wrapping range (e.g. 22-3 meaning 22,23,0,1,2,3)
                if h >= lo or h <= hi:
                    return label
        return "other"

    tz_buckets = collections.Counter()
    for u in target_users:
        h = modal_hour(u)
        if h is None:
            continue
        tz_buckets[bucket_hour(h)] += 1

    stats = {
        "metadata": {
            "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
            "total_messages": len(filtered),
            "channels": sorted(channel_counts.keys()),
            "channel_message_counts": dict(channel_counts),
            "channel_target_message_counts": dict(channel_target_counts),
            # Back-compat alias
            "channel_zh_message_counts": dict(channel_target_counts),
            "date_range": [
                _min_ts(filtered),
                _max_ts(filtered),
            ],
            "target_language": language_profile.code if language_profile else None,
            "target_language_name": language_profile.name if language_profile else None,
            "region": region_profile.code,
            "region_name": region_profile.name,
            "pipeline_version": "1.0.0",
        },
        "language_distribution": dict(lang_counts),
        "users": {
            "total": len(users),
            "target_primary": len(target_primary_users),
            "bilingual": sum(
                1 for u in users.values() if u.language_primary() == "bilingual"
            ),
            "other_primary": sum(
                1 for u in users.values() if u.language_primary() == "other_primary"
            ),
            "silent_or_unclassified": sum(
                1 for u in users.values() if u.language_primary() == "silent"
            ),
            "target_plus_bilingual": len(target_users),
            # Back-compat aliases
            "zh_primary": len(target_primary_users),
            "en_primary": sum(
                1 for u in users.values() if u.language_primary() == "other_primary"
            ),
            "zh_plus_bilingual": len(target_users),
        },
        "retention": {
            "target_active_30d": len(active),
            "target_lapsed_30_90d": len(recently_lapsed),
            "target_lapsed_90d_plus": len(long_lapsed),
            "target_one_time_posters": len(one_time),
            # Back-compat aliases
            "zh_active_30d": len(active),
            "zh_lapsed_30_90d": len(recently_lapsed),
            "zh_lapsed_90d_plus": len(long_lapsed),
            "zh_one_time_posters": len(one_time),
        },
        "location_proxy": dict(tz_buckets),
        "providers": dict(provider_counts.most_common()),
        "competitors": dict(competitor_counts.most_common()),
        "messaging_platforms": dict(messaging_counts.most_common()),
        "features": dict(feature_counts.most_common()),
        "install_paths": dict(install_counts.most_common()),
        "friction_signals": dict(friction_counts.most_common()),
        "shadow_community_mentions": dict(shadow_counts.most_common()),
        "acquisition_markers": dict(acquisition_counts.most_common()),
        "urls": {
            "category_counts": dict(url_category_counts),
            "top_domains": dict(url_domain_counts.most_common(50)),
            "impersonator_domains": dict(impersonator_domain_counts),
            "official_domains": dict(official_domain_counts),
        },
        "help_answered": {
            "total_questions": question_count,
            "target_questions": target_question_count,
            "target_questions_answered_within_48h": target_question_answered,
            "target_answered_rate": (target_question_answered / target_question_count)
            if target_question_count
            else None,
            # Back-compat aliases
            "zh_questions": target_question_count,
            "zh_questions_answered_within_48h": target_question_answered,
            "zh_answered_rate": (target_question_answered / target_question_count)
            if target_question_count
            else None,
        },
    }

    return users, stats


# ----------------------------------------------------------------------------
# Report rendering — simple placeholder substitution
# ----------------------------------------------------------------------------


def render_report(template_path: Path, stats: dict[str, Any]) -> str:
    """Replace {{stats.foo.bar}} placeholders in template with values from stats.

    Supports:
      - dict keys: stats.foo.bar
      - list indices: stats.foo.bar.0  (integer-looking segments)
      - escaping: \\{{stats.foo}} passes through literally as {{stats.foo}}
    """
    text = template_path.read_text(encoding="utf-8")

    # Handle escape: \{{...}} → placeholder that won't match, restored post-pass
    ESCAPE_TOKEN = "\x00ESCAPED_BRACES\x00"
    text = text.replace(r"\{{", ESCAPE_TOKEN)

    def resolver(match: re.Match) -> str:
        path = match.group(1).strip()
        if not path.startswith("stats."):
            return match.group(0)
        parts = path[len("stats.") :].split(".")
        cur: Any = stats
        try:
            for p in parts:
                if isinstance(cur, dict):
                    cur = cur[p]
                elif isinstance(cur, list) and p.isdigit():
                    cur = cur[int(p)]
                else:
                    return f"<missing:{path}>"
            if isinstance(cur, (dict, list)):
                return json.dumps(cur, ensure_ascii=False, indent=2)
            if cur is None:
                return "<none>"
            return str(cur)
        except (KeyError, IndexError, TypeError):
            return f"<missing:{path}>"

    text = re.sub(r"\{\{\s*([^}]+?)\s*\}\}", resolver, text)
    text = text.replace(ESCAPE_TOKEN, "{{")
    return text


# ----------------------------------------------------------------------------
# Salt management
# ----------------------------------------------------------------------------


def ensure_salt(salt_path: Path) -> str:
    if salt_path.exists():
        return salt_path.read_text(encoding="utf-8").strip()
    salt = secrets.token_hex(32)
    salt_path.parent.mkdir(parents=True, exist_ok=True)
    salt_path.write_text(salt, encoding="utf-8")
    salt_path.chmod(0o600)
    print(f"[salt] generated new salt at {salt_path}", file=sys.stderr)
    return salt


# ----------------------------------------------------------------------------
# Stats merging (for --incremental)
# ----------------------------------------------------------------------------


def _merge_counters(old: dict, new: dict) -> dict:
    """Merge two counter dicts by summing values."""
    result = dict(old)
    for k, v in new.items():
        result[k] = result.get(k, 0) + v
    return result


def merge_stats(old: dict, new: dict) -> dict:
    """Merge a new incremental run's stats into the existing accumulated stats.

    Merges all counter-type fields (providers, competitors, friction, etc.)
    by summing. Updates metadata to reflect the combined totals. Retention
    and user counts come from the latest run (they're re-derived from the
    full message set each time, so the new run's values are already
    cumulative for all messages seen so far — not just the new ones).
    """
    merged = dict(new)  # start with new as base (has latest metadata)

    # Merge counter-type top-level fields
    counter_fields = [
        "providers",
        "competitors",
        "messaging_platforms",
        "features",
        "friction_signals",
        "install_paths",
        "shadow_community_mentions",
        "acquisition_channels",
        "language_distribution",
    ]
    for cf in counter_fields:
        if cf in old and cf in new:
            merged[cf] = _merge_counters(old[cf], new[cf])
        elif cf in old:
            merged[cf] = old[cf]

    # Merge URL stats
    if "urls" in old and "urls" in new:
        old_urls = old["urls"]
        new_urls = new["urls"]
        merged_urls = dict(new_urls)
        if "category_counts" in old_urls and "category_counts" in new_urls:
            merged_urls["category_counts"] = _merge_counters(
                old_urls["category_counts"], new_urls["category_counts"]
            )
        if "domain_counts" in old_urls and "domain_counts" in new_urls:
            merged_urls["domain_counts"] = _merge_counters(
                old_urls["domain_counts"], new_urls["domain_counts"]
            )
        merged["urls"] = merged_urls

    # Update metadata: total messages = old + new (new run only processed new msgs)
    old_total = old.get("metadata", {}).get("total_messages", 0)
    new_total = new.get("metadata", {}).get("total_messages", 0)
    merged.setdefault("metadata", {})["total_messages"] = old_total + new_total

    # Merge channel counts
    old_ch = old.get("metadata", {}).get("channel_message_counts", {})
    new_ch = new.get("metadata", {}).get("channel_message_counts", {})
    merged["metadata"]["channel_message_counts"] = _merge_counters(old_ch, new_ch)

    old_ch_t = old.get("metadata", {}).get("channel_target_message_counts", {})
    new_ch_t = new.get("metadata", {}).get("channel_target_message_counts", {})
    merged["metadata"]["channel_target_message_counts"] = _merge_counters(
        old_ch_t, new_ch_t
    )
    merged["metadata"]["channel_zh_message_counts"] = merged["metadata"][
        "channel_target_message_counts"
    ]

    # Date range: widen to encompass both
    old_range = old.get("metadata", {}).get("date_range", [None, None])
    new_range = new.get("metadata", {}).get("date_range", [None, None])
    dates = [d for d in [old_range[0], new_range[0]] if d]
    merged["metadata"]["date_range"] = [
        min(dates) if dates else None,
        max(filter(None, [old_range[1], new_range[1]]))
        if any([old_range[1], new_range[1]])
        else None,
    ]

    # Users and retention: take the new run's values (they reflect the
    # full accumulated message set since the pipeline rebuilds user profiles
    # from scratch each run — this is a known limitation; a true incremental
    # user merge would require per-user delta tracking)
    # But since incremental only passes new messages to run_pipeline, the
    # new stats only reflect new messages. So we need to merge user counts too.
    old_users = old.get("users", {})
    new_users = new.get("users", {})
    merged_users = dict(new_users)
    # User counts: we can't simply sum (same user may appear in both runs)
    # Take the max as a conservative estimate, or the old value if new is 0
    for key in [
        "total",
        "target_primary",
        "bilingual",
        "other_primary",
        "silent_or_unclassified",
        "target_plus_bilingual",
        "zh_primary",
        "en_primary",
        "zh_plus_bilingual",
    ]:
        merged_users[key] = max(old_users.get(key, 0), new_users.get(key, 0))
    merged["users"] = merged_users

    # Help/answered: sum the raw counts
    old_help = old.get("help_answered", {})
    new_help = new.get("help_answered", {})
    merged_help = dict(new_help)
    for key in [
        "total_questions",
        "target_questions",
        "target_answered",
        "total_answered",
    ]:
        merged_help[key] = old_help.get(key, 0) + new_help.get(key, 0)
    # Recalculate rates
    if merged_help.get("total_questions", 0) > 0:
        merged_help["target_answered_rate"] = (
            merged_help.get("target_answered", 0) / merged_help["total_questions"]
        )
        merged_help["overall_answered_rate"] = (
            merged_help.get("total_answered", 0) / merged_help["total_questions"]
        )
    merged["help_answered"] = merged_help

    # Location proxy: sum
    old_loc = old.get("location_proxy", {})
    new_loc = new.get("location_proxy", {})
    merged["location_proxy"] = _merge_counters(old_loc, new_loc)

    # Mark as incremental merge
    merged["metadata"]["incremental_merge"] = True
    merged["metadata"]["previous_total_messages"] = old_total

    return merged
