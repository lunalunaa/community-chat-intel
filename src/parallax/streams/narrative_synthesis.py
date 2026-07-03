#!/usr/bin/env python3
"""narrative_synthesis.py: feed Stream A+B+C+D outputs into a stronger LLM and produce findings_final_v2.md."""

import json
import os
import subprocess
from collections import Counter
from pathlib import Path

BASE = Path(os.environ.get("OUT_DIR", "./out"))
OUT = BASE / "findings_final_v2.md"

# ===== Gather inputs =====
stream_b_findings = json.load((BASE / "stream_b/synthesized_findings.json").open())
stream_c_summary = json.load((BASE / "stream_c/summary.json").open())
stream_c_facts = json.load((BASE / "stream_c/aggregated_facts.json").open())
topics = json.load((BASE / "topics.json").open())
stream_d_pareto = json.load((BASE / "stream_d/user_pareto_v4.json").open())
stream_d_stickiness = json.load((BASE / "stream_d/user_stickiness_v4.json").open())
stream_d_gateway = json.load((BASE / "stream_d/gateway_mix.json").open())
stream_d_reply = json.load((BASE / "stream_d/reply_graph.json").open())
stream_d_temporal = json.load((BASE / "stream_d/temporal_growth_v4.json").open())
stats = json.load((BASE / "stats.json").open())

# Topic distribution
topic_counts = Counter(topics.values())
total_tagged = sum(topic_counts.values())
topic_pcts = {k: (v, round(100 * v / total_tagged, 1)) for k, v in topic_counts.items()}

# Build compact context for the LLM — stay under ~25K chars for safety
#
# NOTE: The ground-truth anchors below are EXAMPLE values from a real run
# (an example ~28K-message community export). Replace COMMUNITY_NAME,
# CORPUS_DESCRIPTION, and GROUND_TRUTH_SUMMARY with your own dataset's facts —
# these are read from env vars so you can drive this script without editing code.
COMMUNITY_NAME = os.environ.get("COMMUNITY_NAME", "the community")
CORPUS_DESCRIPTION = os.environ.get(
    "CORPUS_DESCRIPTION",
    "28,005 messages, 20 days: 2026-04-03 -> 2026-04-23 (example run)",
)
GROUND_TRUTH_SUMMARY = os.environ.get(
    "GROUND_TRUTH_SUMMARY",
    "  - Live membership: 3,124 (3,119 humans + 5 bots)\n"
    "  - Of humans: 878 ever posted a message, 2,241 are pure lurkers (71.8%)\n"
    "  - Of 878 human posters: 103 multi-week active (7+ days), 186 one-time posters\n"
    "  - Message concentration: top 10 human posters = 35.2% of human messages\n"
    "  - Bot message footprint: 138 messages = 0.6% of volume (negligible)\n"
    "  - 3,168 unique join-event names observed in 20 days -> ~49 inferred departures\n",
)

context = f"""You are synthesizing a multi-stream analysis of a chat community ("{COMMUNITY_NAME}", {CORPUS_DESCRIPTION}).

CRITICAL GROUND-TRUTH ANCHORS (verified from the platform's admin UI at export time):
{GROUND_TRUTH_SUMMARY}
Your task: produce a FACTUAL SURVEY WRITEUP — a purely descriptive summary of what the
community talks about, with no strategic recommendations layered in at this stage.

=== STREAM A: BROAD TOPIC DISTRIBUTION ({sum(topic_counts.values())} tagged messages) ===
{json.dumps(topic_pcts, ensure_ascii=False, indent=1)}

=== STREAM B: SEMANTIC-RETRIEVAL NARRATIVE FINDINGS ({len(stream_b_findings)} queries) ===
"""
for qname, f in stream_b_findings.items():
    context += f"\n[{qname}] query: {f['query']}\n{f['analysis'][:900]}\n"

context += (
    "\n\n=== STREAM C: STRUCTURED FACT EXTRACTION (6,571 facts across 244 chunks) ===\n"
)
context += json.dumps(stream_c_summary, ensure_ascii=False, indent=1)[:5000]

# A few exemplar facts per category so MiMo has concrete texture
import random

random.seed(42)
context += "\n\nExemplar facts (randomly sampled, truncated):\n"
for cat, items in stream_c_facts.items():
    if not items:
        continue
    samples = random.sample(items, min(5, len(items)))
    context += f"\n--- {cat} ---\n"
    for s in samples:
        d = {
            k: (
                str(v)[:80]
                if not isinstance(v, list)
                else ",".join(str(x) for x in v)[:80]
            )
            for k, v in s.items()
            if k != "_chunk_idx"
        }
        context += json.dumps(d, ensure_ascii=False) + "\n"

context += f"""

=== STREAM D: QUANTITATIVE MEMBERSHIP/NETWORK ANALYSIS (v4 — ground-truth-anchored) ===

Membership reality (from admin UI + export reconciliation):
  - Live membership: 3,124 (3,119 humans + 5 bots)
  - Human posters: 878 (28.2% of 3,119 humans)
  - Silent lurkers: 2,241 (71.8% of humans)
  - Bot posters: 5 (138 messages = 0.6% of volume)
  - Observed joiners across 20 days: 3,168 unique names
  - Inferred departures (join − current): ~49

Human poster stickiness:
  - Multi-week active (7+ days): 103 (11.7% of posters, 3.3% of all humans)
  - Few-day active (2-6 days): 380 (43.3% of posters)
  - Single-day posters: 209 (23.8% of posters)
  - One-time posters: 186 (21.2% of posters)

Message concentration (human posters over human messages):
{json.dumps(stream_d_pareto["human_concentration"], ensure_ascii=False, indent=1)}

As % of 3,119 humans:
{json.dumps(stream_d_pareto["human_concentration_of_membership"], ensure_ascii=False, indent=1)}

Gateway URL Mix (distinct URL mentions):
{json.dumps(stream_d_gateway["url_mentions_by_gateway"], ensure_ascii=False, indent=1)}

Reply Graph:
- Messages with reply_to: {stream_d_reply["total_messages_with_reply_to"]:,}
- Distinct threads: {stream_d_reply["distinct_threads"]:,}
- Threads with 5+ replies: {stream_d_reply["threads_with_5plus_replies"]}
- Threads with 10+ replies: {stream_d_reply["threads_with_10plus_replies"]}

Temporal growth (first 5, peak day, last 3):
"""
peak_join = max(stream_d_temporal, key=lambda x: x["new_members_joined"])
context += json.dumps(
    stream_d_temporal[:5] + [peak_join] + stream_d_temporal[-3:],
    ensure_ascii=False,
    indent=1,
)

context += f"""

=== AGGREGATE STATS FROM ORIGINAL PIPELINE ===
- Total messages: {stats["metadata"]["total_messages"]:,}
- Language distribution: {stats.get("language_distribution", {})}
- Location proxy: {stats.get("location_proxy", {})}
- Help-answered rate (ZH, threaded 48h): {stats.get("help_answered", {}).get("zh_answered_rate", "n/a")}

=== YOUR TASK ===

Write a comprehensive descriptive survey in markdown with these sections:

1. **Executive Summary** (200 words max) — TL;DR of what this community is and talks about
2. **Who Are They?** — IMPORTANT: anchor membership on the ground-truth numbers above (do not trust any other membership figure derived from message metadata). Discuss the lurker-vs-poster split, any viral spike days, the size of the core engagement cohort, and message concentration among top posters.
3. **What Do They Talk About?** — topic distribution interpreted; what the dominant category means vs the smaller ones
4. **Provider / Gateway Landscape** — what they actually use and why (hosted service, direct APIs, OpenRouter, proxy resellers); include sentiment
5. **Messaging Platform Usage** — Messaging platform breakdown from Stream C messaging_intent + the topic-distribution share for messaging_adapter
6. **Install & Setup Reality** — what install paths they use, what breaks
7. **Competitor Landscape** — this product vs named competitors; include any slang/nickname patterns observed
8. **Brand Identity & Confusion** — new impersonators/clones surfaced, brand-confusion signals
9. **API Key Sharing / Gray Market** — resellers, group purchases, invite codes, leaked keys (cite the actual incident count from Stream C)
10. **Pricing / Token Consumption** — what they complain about
11. **Network / Geographic Friction** — what the friction incidents show
12. **Feature Requests & Success Stories** — what users ASK for and what they BUILD
13. **Help Ecosystem Health** — reply-graph signals, answered-rate — note the denominator caveat (only a fraction of humans ever post, so "help rate" denominators matter)
14. **Notable Quotes / Texture** — 8-10 representative verbatim-style excerpts (paraphrase from the exemplar facts)

Rules:
- This is a SURVEY, not strategy. No P0/P1 recommendations, no "we should..." advice.
- Cite specific numbers wherever possible, ANCHORED TO THE GROUND-TRUTH DATA ABOVE — never a number derived only from message metadata when a verified figure is available.
- Where Stream B, C, and A disagree on the same signal, EXPLAIN WHY (see Limitations discussion in docs/PIPELINE.md for common causes).
- Write in clear, direct English. Don't pad.
- 4,000-6,000 words total.
- Output markdown only. No preamble like "Here is the writeup".
"""

print(f"Context size: {len(context):,} chars", flush=True)

# Call the configured LLM (pro/stronger variant recommended for this step)
cmd = [
    "hermes",
    "chat",
    "-q",
    context,
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
    os.environ.get("LLM_MODEL_PRO", "xiaomi/mimo-v2.5-pro"),
]

print("Calling LLM for synthesis...", flush=True)
import time

t0 = time.time()
r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
elapsed = time.time() - t0
print(f"Got response in {elapsed:.0f}s ({len(r.stdout):,} chars)", flush=True)

out = r.stdout
lines = [l for l in out.split("\n") if not l.startswith("session_id:")]
clean = "\n".join(lines).strip()

# Write
OUT.write_text(clean, encoding="utf-8")
print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)", flush=True)
