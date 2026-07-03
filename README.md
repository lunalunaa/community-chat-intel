# community-chat-intel

**A privacy-preserving toolkit for turning raw chat exports (Discord / Telegram / Feishu-Lark / any JSON export) into structured community-intelligence reports — combining classic NLP heuristics, local embeddings, structured LLM extraction, deterministic analytics, and multi-model synthesis into a single reproducible pipeline.**

Built to answer a real question — *"how does our Chinese-speaking user community actually use our product?"* — without running an intrusive survey. The pipeline extracts the same research signals a poll would have produced (usage patterns, install friction, provider/platform preferences, brand confusion, feature requests) passively from existing chat history, with hashed user IDs and no raw-quote leakage by default.

This repo is the **generalized, open-sourced version** of a project originally built for a real ~3,100-member Chinese-language community chat. All organization-specific branding, strategic recommendations, and live data have been stripped or parameterized; what's left is a reusable framework plus one fully-worked example (with real, illustrative numbers) documented in [`docs/PIPELINE.md`](docs/PIPELINE.md).

## Why this exists / what it demonstrates

- **Multi-stream analysis architecture** — four independent analysis techniques (broad LLM topic tagging, local-embedding semantic retrieval + FAISS, structured LLM fact extraction with tolerant JSON retry, and pure-Python deterministic analytics) run in parallel over the same corpus and get reconciled by a final synthesis pass. Each stream compensates for another's blind spots — see [`docs/PIPELINE.md`](docs/PIPELINE.md) for the full rationale.
- **Ground-truth anchoring** — chat platforms that don't log "member left" events (Feishu/Lark, and effectively most groups without admin logs) make join-event counts systematically overstate current membership. The pipeline pins retention/engagement denominators to a manually-verified live membership count instead of trusting derived numbers.
- **Zero-dependency LLM orchestration** — every LLM call shells out to the user's own [Hermes Agent](https://github.com/NousResearch/hermes-agent) CLI (`hermes chat -q ...`), so there are no API keys hardcoded anywhere in this codebase and switching providers is a one-flag change (`LLM_PROVIDER` / `LLM_MODEL` env vars).
- **Privacy-by-default** — every user ID is SHA-256-hashed with a local salt before it ever reaches a JSON output file; display names are redacted unless explicitly opted in.
- **A generated, self-contained HTML dashboard** — no server, no build step, Chart.js via CDN, data embedded at generation time (see [`docs/DASHBOARD.md`](docs/DASHBOARD.md); dashboard generator lives in the daily-monitoring companion service, not included in this trimmed repo).

## Architecture

```
                     chat_export.jsonl (raw platform export)
                               │
                               │  Stream A (topics.py)
                               │  LLM topic classification, 12 fixed categories
                               │
                 ┌─────────────┼─────────────┐
                 │             │             │
           Stream B       Stream C       Stream D
           ─────────     ─────────     ─────────
           Semantic      Structured    Deterministic
           retrieval     fact extract  Python analytics
           BGE-M3 +      LLM per       (no LLM, free)
           FAISS + LLM   ~100-msg      Pareto, stickiness,
           narrative     chunk         gateway mix, reply
           synthesis                   graph, temporal growth
                 │             │             │
                 └─────────────┼─────────────┘
                               │
                 cross_stream_synthesis.py
                 (single large-context LLM call)
                               │
                     findings_final.md
                               │
                 build_final_report.py
                 (LLM-generated recommendations)
                               │
                       final_report.md
                               │
                 post_analysis.py
                 (brand audit, drills, CSV exports)
```

See [`docs/PIPELINE.md`](docs/PIPELINE.md) for the full architecture writeup, per-stream I/O, gotchas, and cost/runtime estimates from a real run (~110 min, ~$3.65 in LLM inference cost for a 28K-message corpus).

## Quick start

```bash
git clone <this repo>
cd community-chat-intel
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Get a chat export (Discord/Telegram/Lark — see README below for adapters)
#    Result: e.g. ~/Downloads/discord_export.json

# 2. Core keyword-analysis pipeline (seconds for small exports)
python3 analyze.py --input ~/Downloads/discord_export.json --platform discord --out ./out -v

# 3. (Optional) LLM topic tagging — shells out to your configured `hermes` CLI
python3 topics.py --input-chat ~/Downloads/discord_export.json --platform discord \
    --out ./out/topics.json --limit 200

# 4. (Optional) Cross-tabulations
python3 crosstabs.py --users-json ./out/users.json --out ./out/crosstabs.json

# 5. Review ./out/report.md, ./out/stats.json, ./out/crosstabs.md
```

For the full 4-stream deep-analysis pipeline (semantic retrieval, structured fact extraction, deterministic analytics, cross-stream synthesis, final report with recommendations), see [`docs/PIPELINE.md`](docs/PIPELINE.md) — it documents exact commands, environment variables, and a real cost/runtime breakdown.

## Adapting for your own community

All stream scripts (`stream_b_embed_retrieve.py`, `stream_c_fact_extract.py`, `stream_c_retry.py`, `stream_d_v4.py`, `post_analysis.py`, `cross_stream_synthesis.py`, `build_final_report.py`) read their configuration from environment variables instead of hardcoded paths, so you can point the whole pipeline at your own dataset without editing code:

| Variable | Purpose | Default |
|---|---|---|
| `CHAT_JSONL` | Path to the raw NDJSON export | `./data/pages.jsonl` |
| `OUT_DIR` | Output directory for all streams | `./out` |
| `SALT_FILE` | User-ID hashing salt (auto-generate with `analyze.py` on first run) | `./user_hash_salt.key` |
| `GROUND_TRUTH_HUMANS` / `GROUND_TRUTH_BOTS` | Manually-verified live membership (Stream D denominator) | `0` (must be set for meaningful output) |
| `GROUND_TRUTH_SOURCE` | Free-text provenance note for the ground-truth numbers | `"platform admin UI, manually verified"` |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_MODEL_PRO` | Which Hermes-configured provider/model to shell out to | `nous` / `xiaomi/mimo-v2.5` / `xiaomi/mimo-v2.5-pro` |
| `COMMUNITY_NAME`, `CORPUS_DESCRIPTION`, `GROUND_TRUTH_SUMMARY` | Free-text context injected into the cross-stream synthesis prompt | generic examples |
| `SURVEY_SUBJECT`, `STRUCTURAL_CONTEXT`, `RECOMMENDATION_FOCUS_AREAS` | Free-text context injected into the recommendations-generation prompt | generic placeholders |
| `REPORT_TITLE`, `REPORT_SUBJECT`, `REPORT_PERIOD`, `REPORT_CLASSIFICATION` | Front-matter for the final assembled report | generic placeholders |

## Files

| File | Purpose |
|---|---|
| `analyze.py` | Core pipeline (CLI entry point) — adapters, keyword extraction, stats, redaction |
| `topics.py` | Stream A: LLM topic-tagging pass (12 fixed categories) |
| `crosstabs.py` | Cross-tabulation helper (provider × location, feature × retention, etc.) |
| `keywords.py` | Keyword dictionaries — edit this to tune detection for your own product/ecosystem |
| `stream_b_embed_retrieve.py` | Stream B: local embeddings + FAISS semantic search + narrative synthesis |
| `stream_c_fact_extract.py` / `stream_c_retry.py` | Stream C: structured LLM fact extraction + tolerant-JSON retry |
| `stream_d_v4.py` | Stream D: ground-truth-anchored deterministic analytics |
| `cross_stream_synthesis.py` | Feeds all four stream outputs into one LLM call for narrative synthesis |
| `build_final_report.py` | Assembles the final report (methodology + findings + recommendations + limitations) |
| `post_analysis.py` | Brand/impersonator audit, cost-complaint drill, CSV exports |
| `report-template.md` | Report skeleton with `{{stats.xxx}}` placeholders |
| `plan.md` | Research methodology write-up (a full worked example — chat-history-as-survey-substitute) |
| `docs/PIPELINE.md` | Deep architecture doc for the 4-stream pipeline |
| `docs/DASHBOARD.md` | Usage guide for the companion self-contained HTML dashboard |
| `ruff.toml` | Lint config (legacy one-shot scripts get relaxed structural rules) |

## Getting chat exports

- **Discord** — [`DiscordChatExporter`](https://github.com/Tyrrrz/DiscordChatExporter) (GUI/CLI/Docker)
- **Telegram** — Telegram Desktop → group → **Export chat history** → JSON
- **Lark/Feishu** — [`@larksuite/cli`](https://github.com/larksuite/cli), paginating `GET /open-apis/im/v1/messages`
- **Anything else** — write a JSON file matching the canonical schema (documented at the top of `analyze.py`'s `--help`) and use `--platform canonical`

## Privacy & ethics guardrails (enforced by the pipeline)

1. All `author_id` values are SHA-256-hashed with a local salt; raw platform user IDs never appear in `stats.json`.
2. `--keep-names` is default-OFF; display names are replaced with `<redacted>` in `users.json`.
3. The salt file is generated with `secrets.token_hex(32)` and chmod'd `0600` — never commit it, never share it.
4. Direct message quotes should be paraphrased before appearing in any shared report.

## Known limitations

Chinese-language classification is heuristic (CJK-ratio based); question-detection is regex-based; reply-chain structure is platform-dependent; LLM extraction has a small (~1-2%) cross-field bleed rate; short export windows make retention metrics unreliable. Full discussion in `docs/PIPELINE.md` §4 (Limitations & Caveats template inside `build_final_report.py`).

## License

MIT — see [LICENSE](LICENSE).
