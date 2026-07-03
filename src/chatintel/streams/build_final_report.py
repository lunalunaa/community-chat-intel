#!/usr/bin/env python3
"""Build final_report.md — methodology + findings + recommendations + limitations.

Sections:
  - Front matter
  - Executive Summary (from findings_final_v2.md)
  - 1. Methodology (written directly here)
  - 2. Findings (body of findings_final_v2.md minus exec summary)
  - 3. Recommendations (MiMo v2.5-pro generates)
  - 4. Limitations & Caveats (written directly here)
  - 5. Appendices (file inventory)
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

BASE = Path(os.environ.get("OUT_DIR", "./out"))
OUT = BASE / "final_report.md"

# =========================================================================
# Load findings_final_v2.md — split into exec summary vs rest
# =========================================================================
v2_text = (BASE / "findings_final_v2.md").read_text()

# Split: "# ... # 1. Executive Summary ... # 2. ..." — we want exec summary as its own section
# and sections 2-14 as the "Findings" body
# Strategy: split on "## N. " headers
parts = re.split(r"^## (\d+)\. ", v2_text, flags=re.MULTILINE)
# parts[0] = everything before "## 1. " (front matter)
# parts[1] = "1", parts[2] = "Executive Summary\n...\n", parts[3] = "2", parts[4] = "Who Are They?...", etc.
exec_summary = parts[2] if len(parts) > 2 else ""
# Reassemble sections 2..N
body_chunks = []
i = 3
while i + 1 < len(parts):
    body_chunks.append(f"## {int(parts[i]) - 1}. {parts[i + 1].rstrip()}")
    i += 2
findings_body = "\n\n".join(body_chunks)

# =========================================================================
# Input blob for the recommendations generator
# =========================================================================
# Load key summary data
topics = json.load((BASE / "topics.json").open())
from collections import Counter

topic_counts = Counter(topics.values())
total_tagged = sum(topic_counts.values())
topic_dist = {
    k: f"{v:,} ({round(100 * v / total_tagged, 1)}%)"
    for k, v in topic_counts.most_common()
}

stream_c_summary = json.load((BASE / "stream_c/summary.json").open())
pareto = json.load((BASE / "stream_d/user_pareto_v4.json").open())
stream_b_findings = json.load((BASE / "stream_b/synthesized_findings.json").open())

# =========================================================================
# Recommendations prompt — driven by env vars so no org-specific content is
# hardcoded here. Fill these in (or leave the generic example defaults) when
# running against your own dataset. See README.md "Adapting for your own
# community" for the full list of overridable variables.
# =========================================================================
SURVEY_SUBJECT = os.environ.get(
    "SURVEY_SUBJECT", "a community chat (see README for how this was configured)"
)
GROUND_TRUTH_SUMMARY = os.environ.get(
    "GROUND_TRUTH_SUMMARY",
    "- Live membership: 3,124 (3,119 humans + 5 bots) [example values]\n"
    "- 878 human posters, 2,241 silent lurkers (71.8%)\n"
    "- 103 multi-week active users (3.3% of humans)\n"
    "- Top 10 posters = 35.2% of messages\n",
)
STRUCTURAL_CONTEXT = os.environ.get(
    "STRUCTURAL_CONTEXT",
    "(none provided — set STRUCTURAL_CONTEXT to describe any organizational "
    "factors the model should weigh, e.g. competitor relationships, platform "
    "ownership conflicts, existing but undiscoverable features, etc.)",
)
RECOMMENDATION_FOCUS_AREAS = os.environ.get(
    "RECOMMENDATION_FOCUS_AREAS",
    "(none provided — set RECOMMENDATION_FOCUS_AREAS to a newline-separated "
    "list of areas the recommendations should cover, e.g. onboarding UX, "
    "brand/impersonator protection, docs gaps, pricing complaints, etc.)",
)

rec_context = f"""You are writing the RECOMMENDATIONS section for a formal survey report on {SURVEY_SUBJECT}.

=== FULL SURVEY FINDINGS (for grounding; do not repeat them verbatim) ===
{findings_body[:20000]}

=== ADDITIONAL GROUND-TRUTH DATA ===
{GROUND_TRUTH_SUMMARY}

Topic distribution (tagged messages):
{json.dumps(topic_dist, ensure_ascii=False, indent=1)}

Stream C fact counts:
{json.dumps({k: v for k, v in stream_c_summary["overview"].items() if not k.startswith("_")}, ensure_ascii=False, indent=1)}

Known structural context to weigh:
{STRUCTURAL_CONTEXT}

=== YOUR TASK ===

Produce the RECOMMENDATIONS section. Structure:

### A. Decision-Relevant Findings Summary
A concise paragraph of the 5-7 most decision-relevant findings (what matters for action).

### B. Recommendations
Produce 8-14 specific recommendations. For each:
- A clear bold title
- Priority tier: **P0** (immediate, this week), **P1** (this quarter), **P2** (exploratory / next quarter), or **Watch** (monitor but don't act yet)
- 2-4 sentences of rationale, citing specific numbers from the findings
- Cost/effort estimate (Low / Medium / High)
- Expected impact (Low / Medium / High)
- Any caveat or risk

Cover at minimum, where the findings support it:
{RECOMMENDATION_FOCUS_AREAS}

### C. What Is Explicitly NOT Recommended
List 3-5 moves the data does NOT support, with brief reasoning. This is as important as the recommendations — it prevents bad decisions.

### D. Open Questions for Leadership
4-6 questions that the data cannot answer but leadership must resolve to act on the recommendations.

Rules:
- Be decisive. Cite numbers. Don't hedge unnecessarily.
- No marketing fluff. This is for internal strategic review.
- 2,500-3,500 words total.
- Output markdown only. Start directly with "### A. Decision-Relevant Findings Summary". No preamble like "Here are the recommendations".
"""

print(f"Recommendations context: {len(rec_context):,} chars", flush=True)

# Call MiMo
cmd = [
    "hermes",
    "chat",
    "-q",
    rec_context,
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
print("Calling xiaomi/mimo-v2.5-pro for Recommendations section...", flush=True)
t0 = time.time()
r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
elapsed = time.time() - t0
print(f"Got recommendations in {elapsed:.0f}s ({len(r.stdout):,} chars)", flush=True)
out = r.stdout
lines = [
    l
    for l in out.split("\n")
    if not l.startswith("session_id:")
    and not l.startswith("⚠️")
    and "maximum iterations" not in l
    and "file write failed" not in l.lower()
    and not l.startswith("The file")
]
recommendations = "\n".join(lines).strip()
# Strip leading --- separators from TUI leaks
recommendations = re.sub(r"^-{3,}\s*\n", "", recommendations, count=1)

# =========================================================================
# Methodology (written directly)
# =========================================================================
methodology = """## 1. Methodology

### 1.1 Data collection

Data was extracted from the source chat platform using its official export tooling (e.g. `@larksuite/cli` for Feishu/Lark, `DiscordChatExporter` for Discord, Telegram's built-in JSON export). See `README.md` for adapter-specific instructions. The example run this report template was built from used the Lark Open Platform API endpoint `GET /open-apis/im/v1/messages`, paginated at 50 messages per page.

### 1.2 Ground-truth anchoring

Where the platform doesn't reliably emit "member left" events (Feishu/Lark is one such platform), total group membership should be verified directly against the platform's admin UI at export time and passed in via `GROUND_TRUTH_HUMANS` / `GROUND_TRUTH_BOTS` (see `deterministic_analytics.py`). This figure supersedes any membership count derived from join-event system messages, since join counts alone always overstate current membership when leave events aren't logged.

### 1.3 Analysis streams

Four parallel analysis streams were run:

**Stream A — Broad Topic Classification.** Chinese/mixed-language (or your target-language) content messages are classified into a fixed set of topic categories (install_help, install_report, provider_config, messaging_adapter, feature_usage, model_discussion, community_meta, brand_identity, bug_report, feature_request, success_story, general_discussion) via an LLM call per batch, with content-hash caching for resume safety. See `topics.py`.

**Stream B — Semantic Retrieval + Narrative Synthesis.** Non-trivial content messages are embedded locally using `BAAI/bge-m3` (multilingual sentence-transformers, CPU) and indexed with FAISS `IndexFlatIP`. A set of structured retrieval queries (tailored to your research questions) are run against the index; for each, the top-K semantically-closest messages are passed to an LLM to produce a short factual analysis with source references. See `semantic_retrieval.py`.

**Stream C — Structured Fact Extraction.** Content messages are chunked into windows of ≤100 consecutive messages preserving conversational order. Each chunk is passed to an LLM with a JSON schema extracting 10 structured fact types: install_problems, provider_usage (with sentiment), messaging_intent (with intent strength), brand_confusion, api_key_sharing_evidence, pricing_complaints, feature_requests, success_stories, vpn_network_friction, and competitor_mentions. A tolerant-JSON retry pass (`fact_extraction_retry.py`) recovers chunks that fail strict parsing (trailing commas are a common LLM failure mode here).

**Stream D — Deterministic Python Analysis.** Pure-Python computation (no LLM) over the raw export: user Pareto curve, stickiness distribution, gateway URL classification, reply-graph analysis, and temporal growth curves. See `deterministic_analytics.py`.

### 1.4 Final synthesis

All four streams are fed into a stronger/larger model in a single large context window to produce a multi-section narrative survey (`findings_final_v2.md`). The recommendations section of the final report is generated by a separate call with explicit instructions to cite specific numbers and structure priorities as P0/P1/P2/Watch tiers. See `narrative_synthesis.py` and `build_final_report.py`.

### 1.5 Tools & infrastructure

- Chat export: platform-specific official tooling (see README)
- LLM inference: any provider reachable via your LLM CLI's config (or swap in direct API calls)
- Embeddings: `BAAI/bge-m3` (local, CPU, via `sentence-transformers`)
- Vector search: `faiss-cpu`
- Analysis pipeline: this repository's Python package (`chatintel.core.analyze`, `chatintel.streams.*`)

### 1.6 Privacy & redaction

Per-user profiles use SHA-256-hashed user IDs with a local salt file kept outside version control (`.gitignore`'d). Sender display names should be redacted before any external distribution. Raw message content should not be excerpted into external documents without paraphrasing — see `README.md` "Privacy & ethics guardrails"."""

# =========================================================================
# Limitations & Caveats (written directly)
# =========================================================================
limitations = """## 4. Limitations & Caveats

### 4.1 Sample limitations

**Single-chat scope.** A survey like this covers one chat/channel at a time. It is not the entire user base for a product or community — users active on other platforms (forums, other messaging apps, social media) are not captured. Findings generalize only to users who joined *this specific* chat.

**Self-selection bias.** Every user in a chat actively chose to join it. The community may over-represent early adopters and users who follow specific content channels, and under-represent casual users reached through other channels.

**Short time windows distort retention metrics.** If your export window is short (e.g. 20 days), retention metrics beyond "lapsed 30+ days" are definitionally zero. Whether any observed "active core" cohort is stable or itself decaying is unknowable from a single window — rerun periodically to see trends.

**Leave events may not be logged.** Some platforms (Feishu/Lark included) don't emit system messages when users leave or are removed from a group. Churn is then visible only as a residual between join events and live membership; individual-user churn patterns are not recoverable without periodic snapshots.

### 4.2 Instrument limitations

**Cross-tenant/anonymous users may lack display names.** Depending on the platform and privacy settings, some posting user IDs may not resolve to display names via the API. These users' demographic classification (language, location) will be weaker because name-based signals are missing.

**Language classifier is heuristic.** Messages are classified by CJK character ratio (or an equivalent heuristic for other target languages). Code-switched technical text is usually classified correctly as mixed, but very short messages sometimes misclassify. Spot-check a sample before trusting the aggregate.

**LLM-tagged topics have some cross-field bleed.** Stream C extraction can occasionally place fields from one schema category into another. Aggregate distributions are generally trustworthy; per-record field-type purity is not guaranteed.

**Stream A and Stream C may disagree on category volume for the same concept.** Message-level topic classification (Stream A) assigns one dominant label per message, while chunk-level fact extraction (Stream C) can catch sub-thread nuance that gets folded into a different Stream-A label. When they disagree significantly, the Stream C figure is usually closer to reality for that specific signal.

**Reply-graph is threaded-only.** Most `reply_to`-style fields capture explicit threaded replies but not inline `@`-mention responses or adjacent-message answers. Any "help-answered-rate" computed this way is an undercount of true response behavior.

### 4.3 Model & inference limitations

**Fast/cheap classifier models trade some accuracy for throughput.** Running the full pipeline on a frontier reasoning model would likely produce modestly sharper classifications and cleaner extracted facts, at substantially higher cost. Results are believed to be directionally correct, and specifically-cited numbers should be checkable against the source messages in the raw export.

**Sentiment classification is coarse.** Sentiment tags are typically positive/negative/neutral/mixed. Mixed-intent messages tend to bias toward whichever valence the classifier detects first. Net-sentiment figures are directionally reliable but not precise.

### 4.4 Interpretation caveats

**Membership ≠ engagement ≠ mindshare.** A verified membership figure is the correct denominator for retention questions. For questions about influence or opinion leadership, the smaller "active core" posters matter more. Neither figure represents the target population "at large" — just this specific chat.

**Findings about informal economies (resale, key-sharing, etc.) are qualitative, not regulatory advice.** Such evidence is descriptive of community behavior. It does not constitute legal analysis of any policy's terms-of-service compliance or an organization's obligation to act on the findings.

**Competitor/provider mention counts are mention counts, not usage counts.** A user mentioning a competitor product many times may not use it at all — they may be complaining about it. Sentiment-weighted mention analysis partially corrects for this but is not a substitute for real usage-tracking data."""


# =========================================================================
# Appendices
# =========================================================================
def format_size(p):
    try:
        return (
            f"{p.stat().st_size // 1024:>6,} KB"
            if p.stat().st_size > 1024
            else f"{p.stat().st_size:>6,} B "
        )
    except:
        return ""


appendices = """## 5. Appendices

### 5.1 File inventory

Base path: `$OUT_DIR/` (default `./out/`)

**Top-level:**
- `final_report.md` — this document
- `findings_final_v2.md` — narrative survey (authoritative)
- `report.md` — legacy pipeline output (kept for audit trail)
- `stats.json` — machine-readable stats with membership ground truth
- `topics.json` / `topics_by_category.json` — per-message topic labels

**Stream B (semantic retrieval):**
- `stream_b/findings.md` — narrative findings with inline source quotes
- `stream_b/retrieval_results.json` — top-K hits per query
- `stream_b/synthesized_findings.json` — findings as structured JSON
- `stream_b/embeddings.npy` — bge-m3 embeddings
- `stream_b/ids.json` — message-ID ordering for the embedding array

**Stream C (structured facts):**
- `stream_c/aggregated_facts.json` — structured facts across 10 categories
- `stream_c/summary.json` — aggregate counts + breakdowns
- `stream_c/chunks_cache.jsonl` — per-chunk raw output (resume-safe)

**Stream D (deterministic analysis — v4, ground-truth anchored):**
- `stream_d/user_pareto_v4.json` — message concentration
- `stream_d/user_stickiness_v4.json` — retention across posters
- `stream_d/temporal_growth_v4.json` — daily join + post curves
- `stream_d/gateway_mix.json` — URL-classified gateway/provider usage
- `stream_d/reply_graph.json` — conversation-depth stats
- `stream_d/top_20_users.html` — readable timelines of top posters

**Post-analysis drills (one file per category):**
- `post/brand_audit.md` — brand / impersonator audit
- `post/token_consumption.md` — cost-complaint drill
- `post/*.csv` — one CSV per Stream C fact category

**Raw:**
- `../pages.jsonl` (or your platform's export format) — source of truth
- `../users.json` — per-poster profiles (hashed)

### 5.2 Reproducing this analysis

All scripts are in this repository (`src/chatintel/`):
- `core/analyze.py` (`chatintel-analyze`) — keyword-stats pipeline (produces report.md)
- `streams/topics.py` (`chatintel-topics`) — Stream A classifier
- `streams/semantic_retrieval.py` — Stream B embedder + synthesizer
- `streams/fact_extraction.py` — Stream C fact extractor
- `streams/fact_extraction_retry.py` — tolerant-JSON retry for failed chunks
- `streams/deterministic_analytics.py` — ground-truth-anchored deterministic analysis
- `streams/narrative_synthesis.py` — final narrative synthesis
- `streams/post_analysis.py` — brand audit, cost drill, CSV exports
- `streams/build_final_report.py` — this report generator

Rerun with reproducible output by executing them in the order above against your own `pages.jsonl` export. See `docs/PIPELINE.md` for the full execution order and cost/runtime estimates."""

# =========================================================================
# Assemble
# =========================================================================
REPORT_TITLE = os.environ.get("REPORT_TITLE", "Community Survey & Recommendations")
REPORT_SUBJECT = os.environ.get(
    "REPORT_SUBJECT", "(set REPORT_SUBJECT to describe your chat/community)"
)
REPORT_PERIOD = os.environ.get(
    "REPORT_PERIOD", "(set REPORT_PERIOD, e.g. '2026-04-03 -> 2026-04-23')"
)
REPORT_CLASSIFICATION = os.environ.get("REPORT_CLASSIFICATION", "Internal")

header = (
    f"""# {REPORT_TITLE}

**Subject:** {REPORT_SUBJECT}
**Period analyzed:** {REPORT_PERIOD}
**Analyst:** community-chat-intel (autonomous multi-stream pipeline)
**Classification:** {REPORT_CLASSIFICATION}

---

## Executive Summary

"""
    + exec_summary.strip()
    + """

---

"""
)

report = (
    header
    + methodology
    + "\n\n---\n\n## 2. Findings\n\n"
    + findings_body
    + "\n\n---\n\n## 3. Recommendations\n\n"
    + recommendations
    + "\n\n---\n\n"
    + limitations
    + "\n\n---\n\n"
    + appendices
)

OUT.write_text(report, encoding="utf-8")
print(f"\nWrote {OUT}")
print(
    f"Size: {OUT.stat().st_size // 1024} KB, {len(report.split()):,} words, {report.count(chr(10)) + 1} lines"
)
