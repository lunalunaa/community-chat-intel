#!/usr/bin/env python3
"""Stream C (fact_extraction.py): structured fact extraction over conversation chunks.

Splits messages into ~100-message chunks preserving conversational order, feeds
each chunk to an LLM with a structured-output schema, aggregates structured
facts across all chunks. Uses tolerant JSON parsing (trailing-comma stripping,
json5 fallback) on every chunk so a separate retry pass is not needed.

Env vars:
  CHAT_JSONL         Path to raw NDJSON export (default ./data/pages.jsonl)
  OUT_DIR            Output directory (default ./out/stream_c)
  SALT_FILE          User-ID hashing salt (default ./user_hash_salt.key)
  TARGET_LANGUAGE    Language name injected into the extraction prompt (default en)
  TS_UTC_OFFSET_HOURS  UTC offset for tz-less display timestamps (default 0)
  LLM_PROVIDER       LLM CLI provider (default nous)
  LLM_MODEL          LLM CLI model (default: configured by llm_cli.py)
  CONCURRENCY        Parallel chunk extractions (default 4)
"""

import hashlib
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHAT_JSONL = Path(os.environ.get("CHAT_JSONL", "./data/pages.jsonl"))
OUT_DIR = Path(os.environ.get("OUT_DIR", "./out/stream_c"))

TARGET_LANGUAGE = os.environ.get("TARGET_LANGUAGE", "en")
TARGET_LANGUAGE_NAME = {"zh": "Chinese", "en": "English"}.get(
    TARGET_LANGUAGE, TARGET_LANGUAGE
)

SALT_FILE = Path(os.environ.get("SALT_FILE", "./user_hash_salt.key"))
SALT = SALT_FILE.read_text().strip() if SALT_FILE.exists() else "default-salt"

DISPLAY_TS_TZ = timezone(
    timedelta(hours=float(os.environ.get("TS_UTC_OFFSET_HOURS", "0")))
)

CONCURRENCY = int(os.environ.get("CONCURRENCY", "4"))
CHUNK_SIZE = 100


def hash_user(uid):
    if not uid:
        return "unknown"
    return "u_" + hashlib.sha256((SALT + uid).encode()).hexdigest()[:12]


def parse_ts(s):
    if isinstance(s, str) and re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}", s):
        return (
            datetime.strptime(s, "%Y-%m-%d %H:%M")
            .replace(tzinfo=DISPLAY_TS_TZ)
            .astimezone(timezone.utc)
        )
    return None


def format_chunk(chunk):
    out = []
    for m in chunk:
        c = m["content"].replace("\n", " ")[:500]
        out.append(f"[{m['ts']}] {m['name']}: {c}")
    return "\n".join(out)


def call_llm(prompt, timeout=180):
    from parallax.streams.llm_cli import call_llm as _call

    return _call(prompt, timeout=timeout)


def tolerant_json_parse(raw: str):
    """Try strict json first, then strip trailing commas, then json5-ish repair.

    Returns (parsed_dict_or_None, error_str_or_None).
    """
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        return None, "no_json_found"
    body = m.group()
    # 1. strict
    try:
        return json.loads(body), None
    except json.JSONDecodeError:
        pass
    # 2. strip trailing commas: ,] -> ], ,} -> }
    body2 = re.sub(r",(\s*[\]}])", r"\1", body)
    try:
        return json.loads(body2), None
    except json.JSONDecodeError:
        pass
    # 3. try json5 if available (optional soft dependency)
    try:
        import json5  # type: ignore[import-not-found]

        return json5.loads(body), None
    except ImportError:
        pass
    except Exception:
        pass
    # 4. try the last { ... } in case the LLM concatenated multiple outputs
    last = re.findall(r"\{[^\{\}]*(?:\{[^\{\}]*\}[^\{\}]*)*\}", body, re.DOTALL)
    for candidate in reversed(last):
        candidate2 = re.sub(r",(\s*[\]}])", r"\1", candidate)
        try:
            return json.loads(candidate2), None
        except Exception:
            continue
    return None, "all_parsers_failed"


def extract_from_chunk(idx, chunk, extraction_prompt):
    prompt = extraction_prompt + format_chunk(chunk)
    try:
        raw = call_llm(prompt)
    except subprocess.TimeoutExpired:
        return idx, {"_error": "timeout"}
    except subprocess.CalledProcessError as e:
        return idx, {"_error": f"subprocess_error: {e.stderr[:200]}"}
    facts, err = tolerant_json_parse(raw)
    if facts is None:
        return idx, {"_error": err, "_raw": raw[:800]}
    return idx, facts


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ===== Load messages =====
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

    # ===== Chunk =====
    chunks = [messages[i : i + CHUNK_SIZE] for i in range(0, len(messages), CHUNK_SIZE)]
    print(f"[stream_c] {len(chunks)} chunks of ≤{CHUNK_SIZE} messages", flush=True)

    # ===== Extraction prompt (loaded from config) =====
    from parallax.core.config import (
        build_extraction_prompt,
        get_extraction_categories,
        load_fact_schema,
    )

    _fact_schema = load_fact_schema()
    EXTRACTION_PROMPT = build_extraction_prompt(_fact_schema, TARGET_LANGUAGE_NAME)
    CATEGORIES = get_extraction_categories(_fact_schema)

    # ===== Cache (resume-safe) =====
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

    # ===== Run =====
    all_facts = {}
    all_facts.update(cache)

    chunks_to_do = [(i, c) for i, c in enumerate(chunks) if i not in cache]
    print(
        f"[stream_c] {len(chunks_to_do)}/{len(chunks)} chunks to process "
        f"(concurrency={CONCURRENCY})",
        flush=True,
    )

    completed = len(cache)
    t0 = time.time()

    with (
        ThreadPoolExecutor(max_workers=CONCURRENCY) as ex,
        CACHE_FILE.open("a") as cache_fh,
    ):
        futures = {
            ex.submit(extract_from_chunk, i, c, EXTRACTION_PROMPT): i
            for i, c in chunks_to_do
        }
        for fut in as_completed(futures):
            idx, facts = fut.result()
            all_facts[idx] = facts
            cache_fh.write(
                json.dumps({"chunk_idx": idx, "facts": facts}, ensure_ascii=False)
                + "\n"
            )
            cache_fh.flush()
            completed += 1
            elapsed = time.time() - t0
            rate = completed / max(1, elapsed) if elapsed > 0 else 0
            eta = (len(chunks) - completed) / max(0.01, rate) if rate > 0 else 0
            if completed % 5 == 0 or completed == len(chunks):
                print(
                    f"[stream_c] {completed}/{len(chunks)} chunks done "
                    f"({elapsed:.0f}s elapsed, ~{eta:.0f}s ETA)",
                    flush=True,
                )

    # ===== Aggregate =====
    print(f"[stream_c] aggregating facts across {len(all_facts)} chunks", flush=True)

    # CATEGORIES loaded from config above

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

    (OUT_DIR / "aggregated_facts.json").write_text(
        json.dumps(aggregated, indent=2, ensure_ascii=False)
    )
    (OUT_DIR / "extraction_errors.json").write_text(
        json.dumps(errors, indent=2, ensure_ascii=False)
    )

    # Summary
    summary = {cat: len(items) for cat, items in aggregated.items()}
    summary["_total_chunks"] = len(all_facts)
    summary["_successful_chunks"] = len(all_facts) - len(errors)
    summary["_error_chunks"] = len(errors)

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

    if errors:
        print(
            f"\n[stream_c] {len(errors)} chunks still failed after tolerant parsing. "
            f"See extraction_errors.json for details.",
            flush=True,
        )


if __name__ == "__main__":
    main()
