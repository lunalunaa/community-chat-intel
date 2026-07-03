"""Community chat-history analysis pipeline.

Reads a platform-native chat export (Discord JSON, Telegram JSON, or a pre-
normalized canonical JSON), produces:
  - stats.json : aggregated statistics ready for report insertion
  - users.json : per-user profiles (hashed ids)
  - report.md  : report-template.md with stats placeholders filled in

Works for any target-language / region community. Pick a
target language and region with `--target-language` / `--region` (see
`languages.py` for the full list, or add your own language/region profile
there). Defaults to `zh` / `cn` as one fully-worked example; pass
`--target-language none` to disable language classification
entirely (every message counts as "target" — useful for already-monolingual
exports where you don't need the cohort split).

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
import collections
import hashlib
import json
import os
import re
import secrets
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from parallax.core import keywords as kw
from parallax.core import languages as lang

# ----------------------------------------------------------------------------
# Canonical message schema
# ----------------------------------------------------------------------------


@dataclass
class Message:
    platform: str
    channel: str
    message_id: str
    author_id: str  # hashed
    author_name: str  # display-name, redacted in shared outputs
    timestamp: datetime
    content: str
    reply_to_message_id: str | None = None
    reactions: list[dict] = field(default_factory=list)
    attachment_count: int = 0


# ----------------------------------------------------------------------------
# Adapters — one per platform
# ----------------------------------------------------------------------------


def _hash_id(raw_id: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{raw_id}".encode()).hexdigest()[:16]


def load_discord_export(path: Path, salt: str) -> Iterator[Message]:
    """DiscordChatExporter JSON format.

    Structure (abridged):
      {
        "guild": {...},
        "channel": {"id": ..., "name": ...},
        "messages": [
          {
            "id": "...",
            "author": {"id": "...", "name": "...", "nickname": ...},
            "timestamp": "2025-10-01T12:00:00+00:00",
            "content": "...",
            "reference": {"messageId": ...} or null,
            "reactions": [{"emoji": {"name": ...}, "count": ...}],
            "attachments": [...]
          }, ...
        ]
      }
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    channel_name = data.get("channel", {}).get("name", "unknown")
    for msg in data.get("messages", []):
        author = msg.get("author", {}) or {}
        yield Message(
            platform="discord",
            channel=channel_name,
            message_id=str(msg.get("id", "")),
            author_id=_hash_id(str(author.get("id", "")), salt),
            author_name=author.get("nickname") or author.get("name") or "unknown",
            timestamp=_parse_ts(msg.get("timestamp", "")),
            content=msg.get("content") or "",
            reply_to_message_id=(msg.get("reference") or {}).get("messageId"),
            reactions=msg.get("reactions", []),
            attachment_count=len(msg.get("attachments", [])),
        )


def load_telegram_export(path: Path, salt: str) -> Iterator[Message]:
    """Telegram Desktop JSON export format.

    Structure:
      {"name": ..., "type": ..., "id": ..., "messages": [...]}
    Messages have {"id", "type": "message"|"service", "date": ..., "from_id", "from", "text", "reply_to_message_id"}
    `text` can be a string OR a list of mixed strings and {"type": "link"|"mention"|..., "text": ...} objects.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    channel_name = data.get("name", "telegram")
    for msg in data.get("messages", []):
        if msg.get("type") != "message":
            continue
        text = msg.get("text", "")
        if isinstance(text, list):
            text = "".join(x if isinstance(x, str) else x.get("text", "") for x in text)
        from_id = str(msg.get("from_id", ""))
        yield Message(
            platform="telegram",
            channel=channel_name,
            message_id=str(msg.get("id", "")),
            author_id=_hash_id(from_id, salt),
            author_name=msg.get("from") or "unknown",
            timestamp=_parse_ts(msg.get("date", "")),
            content=text,
            reply_to_message_id=(
                str(msg["reply_to_message_id"])
                if msg.get("reply_to_message_id")
                else None
            ),
            reactions=[],
            attachment_count=1 if msg.get("file") or msg.get("photo") else 0,
        )


def load_canonical(path: Path, salt: str) -> Iterator[Message]:
    """Pre-normalized canonical JSON input. Use this to feed in data from
    any platform whose adapter isn't written yet — produce a JSON file with
    {"messages": [<canonical schema dicts>]} and use --platform canonical.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for msg in data.get("messages", []):
        yield Message(
            platform=msg.get("platform", "canonical"),
            channel=msg.get("channel", ""),
            message_id=str(msg.get("message_id", "")),
            author_id=_hash_id(str(msg.get("author_id", "")), salt)
            if not msg.get("author_id", "").startswith(("sha256:", "hash:"))
            else msg["author_id"],
            author_name=msg.get("author_name", "unknown"),
            timestamp=_parse_ts(msg.get("timestamp", "")),
            content=msg.get("content", ""),
            reply_to_message_id=msg.get("reply_to_message_id"),
            reactions=msg.get("reactions", []),
            attachment_count=msg.get("attachment_count", 0),
        )


# ----------------------------------------------------------------------------
# Lark / Feishu export adapter
# ----------------------------------------------------------------------------


def _lark_decode_content(msg_type: str, raw: Any) -> tuple[str, int]:
    """Lark message `content` is a JSON-encoded string keyed by msg_type in the
    raw API, but the `lark-cli im +chat-messages-list` shortcut pre-decodes it
    to plain text. This handles both.

    Returns (plain_text, attachment_count).
    """
    if raw is None or raw == "":
        return ("", 0)

    # Raw API also nests content under "body": {"content": "<json-string>"}
    if isinstance(raw, dict):
        if "content" in raw:
            return _lark_decode_content(msg_type, raw["content"])
        return (f"[{msg_type}]", 0)

    if not isinstance(raw, str):
        return (f"[{msg_type}]", 0)

    # Detect whether `raw` is a JSON-encoded structure (raw API) or
    # a pre-decoded plain string (shortcut layer).
    stripped = raw.lstrip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        # Pre-decoded plain text from the shortcut — determine attachment count
        # from msg_type alone (the shortcut's textification doesn't include
        # structured metadata)
        att = (
            1 if (msg_type or "").lower() in ("image", "file", "audio", "video") else 0
        )
        return (raw, att)

    # Raw API path: JSON-encoded content string
    try:
        c = json.loads(raw)
    except json.JSONDecodeError:
        return (f"[{msg_type}: <unparseable>]", 0)
    if not isinstance(c, dict):
        return (f"[{msg_type}]", 0)

    mt = (msg_type or "").lower()
    if mt == "text":
        return (c.get("text") or "", 0)
    if mt == "post":
        paragraphs = c.get("content") or []
        lines = []
        for para in paragraphs:
            if isinstance(para, list):
                line = "".join(
                    (seg.get("text") or "") for seg in para if isinstance(seg, dict)
                )
                lines.append(line)
        body = "\n".join(lines)
        title = c.get("title") or ""
        return ((f"[title: {title}]\n{body}" if title else body), 0)
    if mt == "image":
        return (f"[Image: {c.get('image_key', '?')}]", 1)
    if mt == "file":
        return (f"[File: {c.get('file_name') or c.get('file_key', '?')}]", 1)
    if mt == "audio":
        return (f"[Audio: {c.get('file_key', '?')}]", 1)
    if mt == "video":
        return (f"[Video: {c.get('file_key', '?')}]", 1)
    if mt == "sticker":
        return (f"[Sticker: {c.get('file_key', '?')}]", 0)
    if mt == "interactive":
        return ("[Card]", 0)
    if mt == "share_chat":
        return (f"[Shared chat: {c.get('chat_id', '?')}]", 0)
    if mt == "share_user":
        return (f"[Shared user: {c.get('user_id', '?')}]", 0)
    if mt == "system":
        # System messages have a template + substitutions
        tmpl = c.get("template") or "event"
        if "from_user" in c or "to_chatters" in c:
            # Render as "<tmpl substitutions>" string
            try:
                rendered = tmpl
                for k, v in c.items():
                    if isinstance(v, list) and k != "divider_text":
                        rendered = rendered.replace(
                            "{" + k + "}", ", ".join(str(x) for x in v)
                        )
                return (f"[System: {rendered}]", 0)
            except Exception:
                pass
        return (f"[System: {tmpl}]", 0)
    return (f"[{msg_type}]", 0)


def _lark_timestamp(raw: Any) -> datetime:
    """Lark timestamps from the raw API are string-encoded milliseconds-since-epoch.
    The shortcut layer reformats them as local-tz display strings like
    "2026-04-23 15:48". Handle all three (ms epoch, seconds epoch, ISO-8601,
    display format) for resilience.
    """
    if raw is None or raw == "":
        return datetime.min.replace(tzinfo=timezone.utc)

    # Try ISO-8601 or display-format strings first
    if isinstance(raw, str):
        # ISO-8601: contains "T" or offset
        if "T" in raw or (
            len(raw) >= 10 and raw[4] == "-" and raw[7] == "-" and "+" in raw[10:]
        ):
            return _parse_ts(raw)
        # Display format: "YYYY-MM-DD HH:MM[:SS]"
        if len(raw) >= 16 and raw[4] == "-" and raw[7] == "-" and raw[10] == " ":
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    # The export tool emits these in LOCAL time with NO tz marker;
                    # assume a fixed offset (default UTC+8, override via
                    # TS_UTC_OFFSET_HOURS env var) to avoid silently misclassifying.
                    offset = float(os.environ.get("TS_UTC_OFFSET_HOURS", "8"))
                    return dt.replace(
                        tzinfo=timezone(timedelta(hours=offset))
                    ).astimezone(timezone.utc)
                except ValueError:
                    continue

    # Numeric epoch path (raw API — string-encoded ms)
    try:
        ms = float(raw)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    if ms > 1e12:
        ms = ms / 1000.0
    try:
        return datetime.fromtimestamp(ms, tz=timezone.utc)
    except (OSError, ValueError, OverflowError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _lark_sender_id(sender: dict) -> str:
    """Lark can nest the user id at any of several paths. Prefer open_id."""
    if not isinstance(sender, dict):
        return ""
    sid = sender.get("sender_id") or {}
    return (
        sid.get("open_id")
        or sid.get("user_id")
        or sender.get("open_id")
        or sender.get("id")
        or sender.get("user_id")
        or ""
    )


def _lark_sender_name(sender: dict, fallback: str) -> str:
    if not isinstance(sender, dict):
        return fallback or "unknown"
    return sender.get("name") or sender.get("nickname") or fallback or "unknown"


def _iter_lark_message_dicts(path: Path) -> Iterator[dict]:
    """Yield raw Lark message dicts from any of the common file shapes lark-cli emits.

    Supported shapes:
      1. NDJSON — one JSON object per line (e.g. `jq -c '.data.items[]' ...`)
      2. JSON array — `[{...}, {...}]`
      3. Full response envelope — `{"code": 0, "data": {"items": [...], "page_token": ...}}`
      4. Concatenated responses — multiple top-level JSON objects in one file
         (the page-token loop pattern in the skill's Step 4 produces this if
         the user forgets `jq -c '.data.items[]'` on each page)
      5. Already-canonical `{"messages": [...]}` — yields the inner messages
    """
    with open(path, "r", encoding="utf-8") as f:
        raw_bytes = f.read()
    raw = raw_bytes.strip()
    if not raw:
        return

    # Case 1: NDJSON — one object per non-blank line, no enclosing structure
    first_line = raw.split("\n", 1)[0].strip()
    if first_line.startswith("{") and not raw.startswith("["):
        # Could be NDJSON OR a single pretty-printed JSON object OR multiple concatenated.
        # Try to parse the whole thing as a single JSON; fall through to NDJSON if that fails.
        try:
            parsed = json.loads(raw)
            # Single-JSON case — dispatch below
            yield from _dispatch_parsed_lark(parsed)
            return
        except json.JSONDecodeError:
            # Try NDJSON (line-by-line)
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield from _dispatch_parsed_lark(obj)
            return

    # Case 2 or 3: JSON array or JSON object
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Case 4: concatenated JSON objects. Use raw_decode to walk.
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(raw):
            # skip whitespace
            while idx < len(raw) and raw[idx].isspace():
                idx += 1
            if idx >= len(raw):
                break
            try:
                obj, end = decoder.raw_decode(raw, idx=idx)
            except json.JSONDecodeError:
                break
            yield from _dispatch_parsed_lark(obj)
            idx = end
        return

    yield from _dispatch_parsed_lark(parsed)


def _dispatch_parsed_lark(obj: Any) -> Iterator[dict]:
    """Given any already-parsed JSON object from a Lark export, yield raw
    message dicts. Handles envelopes, arrays, single messages, and canonical.
    """
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                yield item
        return
    if not isinstance(obj, dict):
        return

    # Already-canonical envelope (top-level "messages" list of canonical dicts)
    if "messages" in obj and isinstance(obj["messages"], list):
        # Distinguish canonical-style (has "author_id"/"platform" fields)
        # from shortcut-style (raw Lark message shape under same key).
        inner = obj["messages"]
        if (
            inner
            and isinstance(inner[0], dict)
            and ("author_id" in inner[0] or inner[0].get("platform") == "canonical")
        ):
            for item in inner:
                if isinstance(item, dict):
                    item.setdefault("_source", "canonical")
                    yield item
            return
        # Otherwise fall through to dispatch as Lark shortcut items
        for item in inner:
            if isinstance(item, dict):
                yield item
        return

    # lark-cli shortcut output envelope:
    #   {"ok": true, "identity": "user", "data": {"has_more": ..., "messages": [...]}}
    data = obj.get("data")
    if isinstance(data, dict):
        if "messages" in data and isinstance(data["messages"], list):
            for item in data["messages"]:
                if isinstance(item, dict):
                    yield item
            return
        # Raw API envelope: {"code":0,"data":{"items":[...]}}
        if "items" in data and isinstance(data["items"], list):
            for item in data["items"]:
                if isinstance(item, dict):
                    yield item
            return

    # Single raw message object (NDJSON pattern)
    if "message_id" in obj or "msg_type" in obj:
        yield obj
        return

    # Unknown shape — skip silently
    return


def load_lark_export(
    path: Path, salt: str, channel: str | None = None
) -> Iterator[Message]:
    """Lark / Feishu `lark-cli im +chat-messages-list` (and related) output.

    Accepts NDJSON, JSON array, full response envelope, concatenated pages, or
    already-canonical `{"messages": [...]}` JSON.

    The Lark `content` field is a JSON-encoded string keyed by msg_type — this
    adapter decodes it to plain text using the same logic as the upstream
    `scripts/lark-to-canonical.sh` helper, so you can point `analyze.py`
    directly at raw lark-cli output.

    `channel` override: since Lark exports don't always carry the chat name
    in the output (pagination loop concatenates bare items), the user should
    pass `--channel "<chat-name>"` at the CLI. If omitted, the adapter
    falls back to the chat_id from the first message, then to "lark-chat".
    """
    msgs = list(_iter_lark_message_dicts(path))

    # Infer channel label if not provided
    if not channel:
        for m in msgs:
            ch = m.get("chat_name") or m.get("chat_id")
            if ch:
                channel = str(ch)
                break
        if not channel:
            channel = "lark-chat"

    for m in msgs:
        if m.get("_source") == "canonical":
            # Pass through canonical dicts without re-decoding content
            yield Message(
                platform=m.get("platform", "lark"),
                channel=m.get("channel") or channel,
                message_id=str(m.get("message_id", "")),
                author_id=_hash_id(str(m.get("author_id", "")), salt),
                author_name=m.get("author_name", "unknown"),
                timestamp=_parse_ts(m.get("timestamp", "")),
                content=m.get("content", ""),
                reply_to_message_id=m.get("reply_to_message_id"),
                reactions=m.get("reactions", []),
                attachment_count=m.get("attachment_count", 0),
            )
            continue

        # Native Lark shape
        msg_type = m.get("msg_type") or "text"
        content_raw = m.get("content") or m.get("body") or ""
        text, attachments = _lark_decode_content(msg_type, content_raw)
        sender = m.get("sender") or {}
        sender_id = _lark_sender_id(sender)
        sender_name = _lark_sender_name(sender, fallback=sender_id)

        # Reply linkage: Lark's native raw-API fields (parent_id/root_id),
        # the shortcut layer's structured `reply_to` object, plus our injected
        # `_parent_message_id` for explicit thread-expansion tooling.
        reply_to_raw = m.get("reply_to")
        reply_to_from_shortcut = None
        if isinstance(reply_to_raw, dict):
            reply_to_from_shortcut = reply_to_raw.get("message_id") or reply_to_raw.get(
                "id"
            )
        elif isinstance(reply_to_raw, str):
            reply_to_from_shortcut = reply_to_raw
        reply_to = (
            m.get("_parent_message_id")
            or m.get("parent_id")
            or m.get("reply_to_message_id")
            or reply_to_from_shortcut
            or (m.get("upper_message_id") if msg_type == "reply" else None)
        )

        # Mentions → add to reactions metadata? No, keep reactions as-is.
        # Emoji reactions are a separate API (`+reactions batch_query`), not in +chat-messages-list.
        reactions = m.get("reactions") or []

        yield Message(
            platform="lark",
            channel=m.get("chat_name") or m.get("chat_id") or channel,
            message_id=str(m.get("message_id") or m.get("id") or ""),
            author_id=_hash_id(sender_id, salt),
            author_name=sender_name,
            timestamp=_lark_timestamp(
                m.get("create_time") or m.get("created_time") or m.get("update_time")
            ),
            content=text,
            reply_to_message_id=str(reply_to) if reply_to else None,
            reactions=reactions,
            attachment_count=attachments,
        )


ADAPTERS = {
    "discord": load_discord_export,
    "telegram": load_telegram_export,
    "canonical": load_canonical,
    "lark": load_lark_export,
}


def _parse_ts(s: str) -> datetime:
    if not s:
        return datetime.min.replace(tzinfo=timezone.utc)
    # handle both "2025-10-01T12:00:00+00:00" and "2025-10-01T12:00:00Z"
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Telegram's "YYYY-MM-DDTHH:MM:SS" with no tz
        try:
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Normalize all timestamps to UTC so downstream hour-of-day / diff math is tz-consistent
    return dt.astimezone(timezone.utc)


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
            "pipeline_version": "0.4.0",
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
        default="zh",
        help="Language code to treat as the 'target' cohort for classification "
        "(see languages.py LANGUAGE_PROFILES for the full list: zh, ja, ko, "
        "ru, ar, he, th, vi, es, fr, de, pt, id, ...). "
        "Pass 'none' to disable language classification entirely — every "
        "message counts as target (useful for already-monolingual exports). "
        "Default: zh (one fully-worked example).",
    )
    parser.add_argument(
        "--region",
        type=str,
        default="cn",
        help="Region code controlling shadow-community platforms and the "
        "timezone-proxy location buckets (see languages.py REGION_PROFILES: "
        "cn, jp, kr, ru, latam, mena, global, ...). Unknown codes fall back "
        "to 'global'. Default: cn (backward-compatible).",
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

    # Write stats.json
    stats_path = args.out / "stats.json"
    stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[write] {stats_path}", file=sys.stderr)

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
