"""Platform-native chat-export adapters.

One ``load_*`` function per supported platform. Each adapter reads the
platform's native export format (DiscordChatExporter JSON, Telegram Desktop
JSON, Slack export zip/dir, Lark/Feishu ``lark-cli`` output, generic CSV, or
a pre-normalized canonical JSON) and yields :class:`Message` instances in the
canonical schema consumed by :mod:`parallax.core.pipeline`.

The canonical :class:`Message` dataclass and the :data:`ADAPTERS` registry
live here so the pipeline module and downstream callers can import them
without a circular dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


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
# Shared timestamp parser (used by every adapter)
# ----------------------------------------------------------------------------


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
                    # assume a fixed offset (default UTC, override via
                    # TS_UTC_OFFSET_HOURS env var) to avoid silently misclassifying.
                    offset = float(os.environ.get("TS_UTC_OFFSET_HOURS", "0"))
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


# ----------------------------------------------------------------------------
# Slack export adapter
# ----------------------------------------------------------------------------


def load_slack_export(path: Path, salt: str) -> Iterator[Message]:
    """Slack export adapter.

    Accepts either:
    - A single channel JSON file (array of message objects)
    - A directory of .json files (one per channel, as exported by Slack)

    Slack message structure (abridged):
      {
        "type": "message",
        "user": "U12345",
        "ts": "1234567890.123456",   # Unix epoch (float as string)
        "text": "...",
        "thread_ts": "1234567890.123456",  # parent message if threaded
        "reactions": [{"name": "thumbsup", "count": 2, "users": [...]}],
        "files": [{"id": "...", "name": "..."}]
      }

    Bot messages (user starting with "B") and message-subtypes like
    "channel_join", "channel_leave" are skipped.
    """
    import zipfile

    files_to_process: list[tuple[str, dict]] = []  # (channel_name, data)

    if path.is_dir():
        for f in sorted(path.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            channel_name = f.stem
            files_to_process.append((channel_name, data))
    elif path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            for name in sorted(zf.namelist()):
                if name.endswith(".json"):
                    data = json.loads(zf.read(name))
                    channel_name = Path(name).stem
                    files_to_process.append((channel_name, data))
    else:
        # Single channel JSON file
        data = json.loads(path.read_text(encoding="utf-8"))
        channel_name = path.stem
        files_to_process.append((channel_name, data))

    for channel_name, data in files_to_process:
        # Slack exports can be a bare array or wrapped in {"messages": [...]}
        msgs = data if isinstance(data, list) else data.get("messages", [])
        for msg in msgs:
            if msg.get("type") != "message":
                continue
            subtype = msg.get("subtype")
            if subtype in (
                "channel_join",
                "channel_leave",
                "channel_name",
                "channel_purpose",
                "channel_topic",
            ):
                continue
            user = msg.get("user", "")
            if user.startswith("B"):  # Bot user
                continue
            ts_str = msg.get("ts", "")
            try:
                ts = datetime.fromtimestamp(float(ts_str), tz=timezone.utc)
            except (ValueError, TypeError):
                ts = _parse_ts(ts_str)
            reactions = [
                {"emoji": r.get("name", ""), "count": r.get("count", 0)}
                for r in msg.get("reactions", [])
            ]
            yield Message(
                platform="slack",
                channel=channel_name,
                message_id=msg.get("ts", ""),
                author_id=_hash_id(user, salt) if user else "unknown",
                author_name=msg.get("user", "unknown"),
                timestamp=ts,
                content=msg.get("text") or "",
                reply_to_message_id=msg.get("thread_ts")
                if msg.get("thread_ts") != ts_str
                else None,
                reactions=reactions,
                attachment_count=len(msg.get("files", [])),
            )


# ----------------------------------------------------------------------------
# Generic CSV adapter
# ----------------------------------------------------------------------------


def load_csv_export(path: Path, salt: str) -> Iterator[Message]:
    """Generic CSV adapter for tabular chat exports.

    Expects at minimum a 'content' column. Recognized columns (case-insensitive):
      - content / text / message       → message text
      - author / user / username / sender  → author name or id
      - author_id / user_id / sender_id → author id (hashed if present)
      - timestamp / ts / time / date    → message timestamp
      - channel / channel_name          → channel label
      - message_id / id                 → message id
      - reply_to / reply_to_message_id  → parent message id

    Unknown columns are ignored. Missing timestamps default to epoch.
    Missing author defaults to 'unknown'. This adapter is designed for
    exports from tools like ChatExporter, custom scripts, or spreadsheet
    dumps where the user maps columns to the expected names.
    """
    import csv

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        # Build column-name lookup (case-insensitive)
        colmap: dict[str, str] = {}
        for field in reader.fieldnames or []:
            colmap[field.lower().strip()] = field

        def get(row: dict, *keys: str) -> str:
            for k in keys:
                col = colmap.get(k.lower())
                if col:
                    val = row.get(col, "")
                    if val:
                        return val.strip()
            return ""

        for row in reader:
            content = get(row, "content", "text", "message")
            if not content:
                continue
            author_name = get(row, "author", "user", "username", "sender")
            author_id_raw = get(row, "author_id", "user_id", "sender_id") or author_name
            ts_str = get(row, "timestamp", "ts", "time", "date")
            channel = get(row, "channel", "channel_name") or "csv-import"
            msg_id = get(row, "message_id", "id")
            reply_to = get(row, "reply_to", "reply_to_message_id")

            yield Message(
                platform="csv",
                channel=channel,
                message_id=msg_id,
                author_id=_hash_id(author_id_raw, salt) if author_id_raw else "unknown",
                author_name=author_name or "unknown",
                timestamp=_parse_ts(ts_str),
                content=content,
                reply_to_message_id=reply_to or None,
                reactions=[],
                attachment_count=0,
            )


ADAPTERS = {
    "discord": load_discord_export,
    "telegram": load_telegram_export,
    "canonical": load_canonical,
    "lark": load_lark_export,
    "slack": load_slack_export,
    "csv": load_csv_export,
}
