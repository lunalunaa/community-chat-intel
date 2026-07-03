#!/usr/bin/env python3
"""Stream B (semantic_retrieval.py): local embeddings + retrieval queries.

Embeds all non-system messages with a multilingual model, builds a FAISS index,
runs structured retrieval queries, feeds top-K results to an LLM for synthesis.

Set TARGET_LANGUAGE to pick which QUERIES_BY_LANGUAGE example set to run
(defaults to "zh" for backward compatibility with the original worked
example; "en" is also provided — add your own entry for other languages).
Set TS_UTC_OFFSET_HOURS if your export's display-format timestamps are in
local time other than China Standard Time (the default).

Uses local sentence-transformers (no API) for embeddings; the LLM synthesis
step shells out to `hermes chat -q` so any configured provider/model works —
override via LLM_PROVIDER / LLM_MODEL env vars (defaults shown are just an
example; edit the `cmd` list below if your LLM CLI isn't named `hermes`).
"""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHAT_JSONL = Path(os.environ.get("CHAT_JSONL", "./data/pages.jsonl"))
OUT_DIR = Path(os.environ.get("OUT_DIR", "./out/stream_b"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Target language for the QUERIES set below and the LLM synthesis prompt.
# Defaults to "zh" for backward compatibility with the original worked
# example. Set to any languages.py LANGUAGE_PROFILES code, or add your own
# entry to QUERIES_BY_LANGUAGE.
TARGET_LANGUAGE = os.environ.get("TARGET_LANGUAGE", "zh")
TARGET_LANGUAGE_NAME = {"zh": "Chinese", "en": "English"}.get(
    TARGET_LANGUAGE, TARGET_LANGUAGE
)

# Timestamp parsing assumes a fixed UTC offset for the "YYYY-MM-DD HH:MM"
# display-format timestamps some export tools emit without a tz marker.
# Defaults to +8 (China Standard Time) for backward compatibility with the
# original worked example; set TS_UTC_OFFSET_HOURS to your
# own export's local timezone offset (e.g. 9 for Japan/Korea, 0 for UTC).
TS_UTC_OFFSET_HOURS = float(os.environ.get("TS_UTC_OFFSET_HOURS", "8"))

print("[stream_b] loading sentence-transformers...", flush=True)
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-m3"  # multilingual, supports 100+ languages for dense retrieval
print(f"[stream_b] loading model: {MODEL_NAME}", flush=True)
model = SentenceTransformer(MODEL_NAME)

# ===== Load and prep messages =====
DISPLAY_TS_TZ = timezone(timedelta(hours=TS_UTC_OFFSET_HOURS))


def parse_ts(s):
    if isinstance(s, str) and re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}", s):
        return (
            datetime.strptime(s, "%Y-%m-%d %H:%M")
            .replace(tzinfo=DISPLAY_TS_TZ)
            .astimezone(timezone.utc)
        )
    return None


print("[stream_b] loading messages...", flush=True)
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
    content = content.strip()
    if len(content) < 5:  # skip empty/trivial
        continue
    sender = m.get("sender") or {}
    messages.append(
        {
            "id": m.get("message_id", ""),
            "content": content[:1500],  # embed first 1500 chars to stay in model ctx
            "ts": m.get("create_time", ""),
            "sender_name": sender.get("name", ""),
        }
    )
print(f"[stream_b] {len(messages):,} messages to embed", flush=True)

# ===== Embed (or load cached) =====
emb_cache = OUT_DIR / "embeddings.npy"
ids_cache = OUT_DIR / "ids.json"

embs: "np.ndarray | None" = None
if emb_cache.exists() and ids_cache.exists():
    print(f"[stream_b] loading cached embeddings from {emb_cache}", flush=True)
    loaded = np.load(str(emb_cache))
    cached_ids = json.loads(ids_cache.read_text())
    if cached_ids == [m["id"] for m in messages]:
        print("[stream_b] cache matches; skipping embed pass", flush=True)
        embs = loaded
    else:
        print("[stream_b] cache mismatch; re-embedding", flush=True)

if embs is None:
    print(
        "[stream_b] embedding... (this is the slow part, ~2-5 min on CPU)", flush=True
    )
    import time

    t0 = time.time()
    texts = [m["content"] for m in messages]
    encoded = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    embs = np.asarray(encoded)
    elapsed = time.time() - t0
    print(
        f"[stream_b] embedded {len(texts):,} messages in {elapsed:.0f}s ({len(texts) / elapsed:.0f}/s)",
        flush=True,
    )
    np.save(str(OUT_DIR / "embeddings.npy"), embs.astype("float32"))
    (OUT_DIR / "ids.json").write_text(json.dumps([m["id"] for m in messages]))

# ===== Build FAISS index =====
print(f"[stream_b] building FAISS index (dim={embs.shape[1]})", flush=True)
index = faiss.IndexFlatIP(
    embs.shape[1]
)  # inner product == cosine on normalized vectors
index.add(embs.astype("float32"))

# ===== Retrieval queries (loaded from config) =====
from parallax.core.config import load_queries

QUERIES_BY_LANGUAGE = load_queries()

QUERIES = QUERIES_BY_LANGUAGE.get(TARGET_LANGUAGE, QUERIES_BY_LANGUAGE.get("en", {}))
if TARGET_LANGUAGE not in QUERIES_BY_LANGUAGE:
    print(
        f"[stream_b] no QUERIES set for TARGET_LANGUAGE={TARGET_LANGUAGE!r}; "
        f"falling back to the 'en' example set. Add your own entry to "
        f"queries.yaml for a language-native query set.",
        flush=True,
    )

print(f"[stream_b] running {len(QUERIES)} retrieval queries", flush=True)
TOP_K = 30
retrieval_out = {}
for query_name, query_text in QUERIES.items():
    q_emb = model.encode(
        [query_text], normalize_embeddings=True, convert_to_numpy=True
    ).astype("float32")
    D, I = index.search(q_emb, TOP_K)
    hits = []
    for rank, (idx, score) in enumerate(zip(I[0], D[0])):
        if idx == -1:
            continue
        m = messages[idx]
        hits.append(
            {
                "rank": rank + 1,
                "score": float(score),
                "message_id": m["id"],
                "ts": m["ts"],
                "sender": m["sender_name"],
                "content": m["content"][:500],
            }
        )
    retrieval_out[query_name] = {
        "query": query_text,
        "hits": hits,
    }
    print(
        f'  [{query_name}] top score={hits[0]["score"]:.3f}  "{hits[0]["content"][:60]}..."',
        flush=True,
    )

(OUT_DIR / "retrieval_results.json").write_text(
    json.dumps(retrieval_out, indent=2, ensure_ascii=False)
)
print(f"[stream_b] retrieval done → {OUT_DIR / 'retrieval_results.json'}", flush=True)

# ===== LLM synthesis for each query =====
print()
print("[stream_b] synthesizing findings with your configured LLM...", flush=True)

findings = {}
for query_name, data in retrieval_out.items():
    prompt_lines = [
        f"You are analyzing a {TARGET_LANGUAGE_NAME}-language AI-product community chat. "
        f"Below are the {TOP_K} most-relevant messages for this research query:",
        f"QUERY: {query_name}",
        f"QUERY_TEXT: {data['query']}",
        "",
        "MESSAGES (ranked by semantic similarity, highest first):",
    ]
    for h in data["hits"]:
        prompt_lines.append(f"[{h['rank']}] (score={h['score']:.2f}) {h['content']}")
    prompt_lines += [
        "",
        "TASK: Write a concise 150-200 word English analysis answering what these messages collectively reveal about this topic. Quote message numbers in brackets as evidence (e.g., '[3]'). Be specific and factual. If signal is weak/ambiguous, say so explicitly. Do not pad.",
    ]
    prompt = "\n".join(prompt_lines)

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
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=True)
        out = r.stdout
        # strip session_id line
        lines = out.split("\n")
        clean = "\n".join(l for l in lines if not l.startswith("session_id:")).strip()
        findings[query_name] = {
            "query": data["query"],
            "analysis": clean,
            "source_count": len(data["hits"]),
        }
        print(f"  ✓ {query_name} ({len(clean)} chars)", flush=True)
    except subprocess.TimeoutExpired:
        findings[query_name] = {
            "query": data["query"],
            "analysis": "[TIMEOUT]",
            "source_count": len(data["hits"]),
        }
        print(f"  ✗ {query_name} timeout", flush=True)
    except subprocess.CalledProcessError as e:
        findings[query_name] = {
            "query": data["query"],
            "analysis": f"[ERROR: {e.stderr[:200]}]",
            "source_count": len(data["hits"]),
        }
        print(f"  ✗ {query_name} error", flush=True)

(OUT_DIR / "synthesized_findings.json").write_text(
    json.dumps(findings, indent=2, ensure_ascii=False)
)

# Also write a readable markdown version
md_lines = [
    "# Stream B — Semantic Retrieval Findings",
    "",
    f"Corpus: {len(messages):,} messages embedded with {MODEL_NAME}, synthesized via LLM",
    f"Queries: {len(QUERIES)}",
    "",
    "---",
    "",
]
for q, f in findings.items():
    md_lines += [
        f"## {q}",
        f"_Query: {f['query']}_",
        "",
        f"{f['analysis']}",
        "",
        "---",
        "",
    ]
(OUT_DIR / "findings.md").write_text("\n".join(md_lines), encoding="utf-8")

print(
    f"[stream_b] DONE. {len(findings)} findings written to {OUT_DIR / 'findings.md'}",
    flush=True,
)
