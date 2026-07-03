#!/usr/bin/env python3
"""Stream C (fact_extraction.py): structured fact extraction over conversation chunks.

Splits messages into ~100-message chunks preserving conversational order, feeds
each chunk to an LLM with a structured-output schema, aggregates structured
facts across all chunks. See fact_extraction_retry.py for the tolerant-JSON
retry pass over any chunks that fail strict parsing.
"""

import hashlib
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHAT_JSONL = Path(os.environ.get("CHAT_JSONL", "./data/pages.jsonl"))
OUT_DIR = Path(os.environ.get("OUT_DIR", "./out/stream_c"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Target language, used only to phrase the extraction prompt below (does not
# affect which messages get chunked/extracted — this stream processes all
# non-system messages regardless of language).
TARGET_LANGUAGE = os.environ.get("TARGET_LANGUAGE", "zh")
TARGET_LANGUAGE_NAME = {"zh": "Chinese", "en": "English"}.get(
    TARGET_LANGUAGE, TARGET_LANGUAGE
)

SALT_FILE = Path(os.environ.get("SALT_FILE", "./user_hash_salt.key"))
SALT = SALT_FILE.read_text().strip() if SALT_FILE.exists() else "default-salt"


def hash_user(uid):
    if not uid:
        return "unknown"
    return "u_" + hashlib.sha256((SALT + uid).encode()).hexdigest()[:12]


# Timestamp parsing assumes a fixed UTC offset for "YYYY-MM-DD HH:MM"
# display-format timestamps some export tools emit without a tz marker.
# Defaults to +8 (China Standard Time) for backward compatibility with the
# original Feishu-export worked example; set TS_UTC_OFFSET_HOURS to your
# own export's local timezone offset (e.g. 9 for Japan/Korea, 0 for UTC).
DISPLAY_TS_TZ = timezone(
    timedelta(hours=float(os.environ.get("TS_UTC_OFFSET_HOURS", "8")))
)


def parse_ts(s):
    if isinstance(s, str) and re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}", s):
        return (
            datetime.strptime(s, "%Y-%m-%d %H:%M")
            .replace(tzinfo=DISPLAY_TS_TZ)
            .astimezone(timezone.utc)
        )
    return None


print("[stream_c] loading messages...", flush=True)
messages = []
for line in CHAT_JSONL.open():
    try:
        m = json.loads(line)
    except json.JSONDecodeError:
        continue
    if m.get("msg_type") == "system":
        continue
    content = m.get("content") or ""
    if isinstance(content, dict):
        content = content.get("text", "") or json.dumps(content, ensure_ascii=False)
    if not isinstance(content, str):
        content = str(content)
    if len(content.strip()) < 3:
        continue
    sender = m.get("sender") or {}
    uid = sender.get("id") or sender.get("open_id") or ""
    messages.append(
        {
            "id": m.get("message_id", ""),
            "uhash": hash_user(uid),
            "name": sender.get("name", "?"),
            "ts": m.get("create_time", ""),
            "content": content.strip()[:800],
        }
    )

messages.sort(key=lambda x: x["ts"])
print(f"[stream_c] {len(messages):,} messages loaded", flush=True)

# ===== Chunk into windows of ~100 messages =====
CHUNK_SIZE = 100
chunks = [messages[i : i + CHUNK_SIZE] for i in range(0, len(messages), CHUNK_SIZE)]
print(f"[stream_c] {len(chunks)} chunks of ≤{CHUNK_SIZE} messages", flush=True)

EXTRACTION_PROMPT = (
    f"You are analyzing a chunk of chat messages from a product's community chat "
    f"({TARGET_LANGUAGE_NAME}-language, on a chat platform). Extract structured "
    "facts. Output a single valid JSON object matching this schema (omit arrays "
    "that have no instances):\n"
    + """
{
  "install_problems": [{"user_ref": "a short tag like 'user_A' or actual @name", "problem": "what broke", "os_or_context": "optional", "resolved": true/false/null}],
  "provider_usage": [{"user_ref": "...", "provider_or_gateway": "hosted_service | openrouter | direct_kimi | direct_minimax | direct_glm | direct_volcengine | direct_deepseek | direct_qwen | proxy_reseller | self_hosted | anthropic | openai | other", "sentiment": "positive | negative | neutral", "quoted_context": "short"}],
  "messaging_intent": [{"user_ref": "...", "platform": "feishu | wechat | dingtalk | qq | slack | discord | telegram | lark_intl | other", "intent": "exploring | wants_adapter | actively_building | using_via_existing_adapter", "context": "short"}],
  "brand_confusion": [{"user_ref": "...", "question": "what they asked", "resolution": "answered | unanswered | conflicting"}],
  "api_key_sharing_evidence": [{"user_ref": "...", "type": "offering | seeking | reselling | group_purchase", "details": "short"}],
  "pricing_complaints": [{"user_ref": "...", "service": "what", "issue": "short"}],
  "feature_requests": [{"user_ref": "...", "feature": "what they want", "use_case": "short"}],
  "success_stories": [{"user_ref": "...", "what_built": "short", "tools_used": ["skills", "memory", "cron", "mcp", ...]}],
  "vpn_network_friction": [{"user_ref": "...", "issue": "short", "workaround": "optional"}],
  "competitor_mentions": [{"user_ref": "...", "competitor": "competitor_a | competitor_b | competitor_c | other", "stance": "favoring_product | favoring_competitor | neutral_comparison"}]
}

Rules:
- Only extract facts actually supported by the messages. No speculation.
- If a chunk is mostly off-topic chatter, return mostly empty arrays.
- Use actual user names from messages when present (anonymize only if clearly harmful).
- Keep all field values concise (<50 chars where possible).
- Output ONLY the JSON object, no prose before or after.

MESSAGES:
"""
)


def format_chunk(chunk):
    out = []
    for m in chunk:
        # truncate long contents, include sender
        c = m["content"].replace("\n", " ")[:500]
        out.append(f"[{m['ts']}] {m['name']}: {c}")
    return "\n".join(out)


def call_kimi(prompt, timeout=180):
    cmd = [
        "hermes",
        "chat",
        "-q",
        prompt,
        "--quiet",
        "--ignore-rules",
        "--ignore-user-config",
        "--max-turns",
        "1",
        "--source",
        "tool",
        "--provider",
        os.environ.get("LLM_PROVIDER", "nous"),
        "--model",
        os.environ.get("LLM_MODEL", "xiaomi/mimo-v2.5"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    out = r.stdout
    lines = [l for l in out.split("\n") if not l.startswith("session_id:")]
    return "\n".join(lines).strip()


def extract_from_chunk(idx, chunk):
    prompt = EXTRACTION_PROMPT + format_chunk(chunk)
    try:
        raw = call_kimi(prompt)
    except subprocess.TimeoutExpired:
        return idx, {"_error": "timeout"}
    except subprocess.CalledProcessError as e:
        return idx, {"_error": f"subprocess_error: {e.stderr[:200]}"}

    # strip markdown fences, find json object
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        return idx, {"_error": "no_json_found", "_raw": raw[:500]}
    try:
        facts = json.loads(m.group())
        return idx, facts
    except json.JSONDecodeError as e:
        return idx, {"_error": f"json_parse_failed: {e}", "_raw": raw[:500]}


# ===== Cache =====
CACHE_FILE = OUT_DIR / "chunks_cache.jsonl"
cache = {}
if CACHE_FILE.exists():
    for line in CACHE_FILE.open():
        try:
            d = json.loads(line)
            cache[d["chunk_idx"]] = d["facts"]
        except Exception:
            pass
    print(f"[stream_c] loaded {len(cache)} cached chunks", flush=True)

# ===== Run with concurrency =====
CONCURRENCY = 4
all_facts = {}

chunks_to_do = [(i, c) for i, c in enumerate(chunks) if i not in cache]
print(
    f"[stream_c] {len(chunks_to_do)}/{len(chunks)} chunks to process (concurrency={CONCURRENCY})",
    flush=True,
)

completed = len(cache)
all_facts.update(cache)

import time

t0 = time.time()
with (
    ThreadPoolExecutor(max_workers=CONCURRENCY) as ex,
    CACHE_FILE.open("a") as cache_fh,
):
    futures = {ex.submit(extract_from_chunk, i, c): i for i, c in chunks_to_do}
    for fut in as_completed(futures):
        idx, facts = fut.result()
        all_facts[idx] = facts
        cache_fh.write(
            json.dumps({"chunk_idx": idx, "facts": facts}, ensure_ascii=False) + "\n"
        )
        cache_fh.flush()
        completed += 1
        elapsed = time.time() - t0
        rate = completed / max(1, elapsed) if elapsed > 0 else 0
        eta = (len(chunks) - completed) / max(0.01, rate) if rate > 0 else 0
        if completed % 5 == 0 or completed == len(chunks):
            print(
                f"[stream_c] {completed}/{len(chunks)} chunks done ({elapsed:.0f}s elapsed, ~{eta:.0f}s ETA)",
                flush=True,
            )

# ===== Aggregate =====
print(f"[stream_c] aggregating facts across {len(all_facts)} chunks", flush=True)

CATEGORIES = [
    "install_problems",
    "provider_usage",
    "messaging_intent",
    "brand_confusion",
    "api_key_sharing_evidence",
    "pricing_complaints",
    "feature_requests",
    "success_stories",
    "vpn_network_friction",
    "competitor_mentions",
]

aggregated = {c: [] for c in CATEGORIES}
errors = []
for idx, facts in sorted(all_facts.items()):
    if "_error" in facts:
        errors.append({"chunk_idx": idx, "error": facts["_error"]})
        continue
    for cat in CATEGORIES:
        items = facts.get(cat, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    item["_chunk_idx"] = idx
                    aggregated[cat].append(item)

# Save full aggregated
(OUT_DIR / "aggregated_facts.json").write_text(
    json.dumps(aggregated, indent=2, ensure_ascii=False)
)
(OUT_DIR / "extraction_errors.json").write_text(
    json.dumps(errors, indent=2, ensure_ascii=False)
)

# Summary counts
summary = {cat: len(items) for cat, items in aggregated.items()}
summary["_total_chunks"] = len(all_facts)
summary["_successful_chunks"] = len(all_facts) - len(errors)
summary["_error_chunks"] = len(errors)

# Sub-categorizations
provider_counts = {}
for item in aggregated["provider_usage"]:
    p = item.get("provider_or_gateway", "unknown")
    sentiment = item.get("sentiment", "neutral")
    key = f"{p}_{sentiment}"
    provider_counts[key] = provider_counts.get(key, 0) + 1

messaging_intent_counts = {}
for item in aggregated["messaging_intent"]:
    key = f"{item.get('platform', 'unknown')}_{item.get('intent', 'unknown')}"
    messaging_intent_counts[key] = messaging_intent_counts.get(key, 0) + 1

competitor_counts = {}
for item in aggregated["competitor_mentions"]:
    key = f"{item.get('competitor', 'unknown')}_{item.get('stance', 'unknown')}"
    competitor_counts[key] = competitor_counts.get(key, 0) + 1

(OUT_DIR / "summary.json").write_text(
    json.dumps(
        {
            "overview": summary,
            "provider_usage_breakdown": provider_counts,
            "messaging_intent_breakdown": messaging_intent_counts,
            "competitor_breakdown": competitor_counts,
        },
        indent=2,
        ensure_ascii=False,
    )
)

print(
    f"[stream_c] DONE. {len(all_facts) - len(errors)} successful, {len(errors)} errors",
    flush=True,
)
for cat, count in summary.items():
    if not cat.startswith("_"):
        print(f"    {cat}: {count}", flush=True)
