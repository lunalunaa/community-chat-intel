# parallax

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/Code%20style-ruff-261230.svg)](https://docs.astral.sh/ruff/)
[![Type checker: basedpyright](https://img.shields.io/badge/Type%20checker-basedpyright-orange.svg)](https://docs.basedpyright.com/)
[![Package manager: uv](https://img.shields.io/badge/uv-managed-de4c4a.svg)](https://docs.astral.sh/uv/)
[![CI](https://github.com/lunalunaa/parallax/actions/workflows/ci.yml/badge.svg)](https://github.com/lunalunaa/parallax/actions/workflows/ci.yml)

Turn raw chat exports (Discord / Telegram / Lark / any JSON) into structured community-intelligence reports — passively, without running a survey. Combines NLP heuristics, local embeddings (BGE-M3 + FAISS), structured LLM fact extraction, deterministic analytics, and multi-model synthesis into one reproducible pipeline. User IDs are SHA-256-hashed by default; no raw quotes leak into outputs.

Multi-language and multi-region out of the box — pick your target market with `--target-language` / `--region`, or add your own `LanguageProfile` + `RegionProfile`. Ships with 13 languages and 7 regions as fully-worked examples.

---

## Quick start

```bash
git clone https://github.com/lunalunaa/parallax.git
cd parallax

# Install (pick one):
uv sync --extra dev          # uv (recommended)
# — or —
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# Run:
parallax-analyze --input ~/Downloads/discord_export.json --platform discord \
    --target-language ja --region jp --out ./out -v

# Optional: LLM topic tagging + cross-tabulations
parallax-topics --input-chat ~/Downloads/discord_export.json --platform discord \
    --target-language ja --out ./out/topics.json
parallax-crosstabs --users-json ./out/users.json --region jp --out ./out/crosstabs.json
```

> **First install is slow** (~1–2 GB for `sentence-transformers` / `faiss-cpu` / `torch`). This is expected.

<details>
<summary><b>Editor / Jupyter kernel setup (Zed, VS Code, JupyterLab)</b></summary>

This repo ships a `pyrightconfig.json` pointing at `.venv`. If your editor shows "missing import" errors or `Kernel error: No module named ipykernel_launcher`, it's using the wrong interpreter. Fix:

```bash
pip install -e ".[dev]"   # or: uv pip install -e ".[dev]"
python -m ipykernel install --user --name=parallax --display-name="parallax (.venv)"
```

Then select **"parallax (.venv)"** in your editor's kernel/interpreter picker. Verify with `basedpyright .` (should report 0 errors).

</details>

## Architecture

```
              chat_export.jsonl
                    │
         ┌──────────┼──────────┐
         │          │          │
    Stream B    Stream C    Stream D
    Semantic    Structured  Deterministic
    retrieval   fact extract  analytics
    BGE-M3 +    LLM per      (no LLM)
    FAISS       ~100-msg
                chunk
         │          │          │
         └──────────┼──────────┘
                    │
         narrative_synthesis.py
         (one large-context LLM call)
                    │
              build_final_report.py
                    │
              final_report.md
```

Stream A (`topics.py`) runs first as broad LLM topic classification. See [`docs/PIPELINE.md`](docs/PIPELINE.md) for the full writeup, per-stream I/O, and a real cost breakdown (~110 min, ~$3.65 for 28K messages).

The remaining stream scripts are one-shot modules (no `main()`):

```bash
python -m parallax.streams.semantic_retrieval
python -m parallax.streams.fact_extraction
python -m parallax.streams.deterministic_analytics
python -m parallax.streams.narrative_synthesis
python -m parallax.streams.build_final_report
python -m parallax.streams.post_analysis
```

## Language / region support

| `--target-language` | Language | Detection | `--region` | Region |
|---|---|---|---|---|
| `zh` (default) | Chinese | CJK script ratio | `cn` (default) | Greater China |
| `ja` | Japanese | Hiragana/Katakana + CJK | `jp` | Japan |
| `ko` | Korean | Hangul script ratio | `kr` | Korea |
| `ru` | Russian | Cyrillic script ratio | `ru` | Russia/CIS |
| `ar` | Arabic | Arabic script ratio | `latam` | Latin America |
| `he` | Hebrew | Hebrew script ratio | `mena` | Middle East/N. Africa |
| `th` | Thai | Thai script ratio | `global` | Global/English-default |
| `vi` | Vietnamese | Vietnamese-diacritic | | |
| `es` `fr` `de` `pt` `id` | Latin-script | Stopword-frequency (lower precision) | | |
| `none` | — | Disables language split | | |

Add your own market by adding one entry to [`src/parallax/core/languages.py`](src/parallax/core/languages.py) — no code changes elsewhere.

## Configuration

All stream scripts read from environment variables — no hardcoded paths to edit:

| Variable | Purpose | Default |
|---|---|---|
| `CHAT_JSONL` | Path to raw NDJSON export | `./data/pages.jsonl` |
| `OUT_DIR` | Output directory for all streams | `./out` |
| `SALT_FILE` | User-ID hashing salt | `./user_hash_salt.key` |
| `TARGET_LANGUAGE` | Which query set + LLM prompt language | `zh` |
| `TS_UTC_OFFSET_HOURS` | UTC offset for tz-less display timestamps | `8` (CST) |
| `GROUND_TRUTH_HUMANS` / `GROUND_TRUTH_BOTS` | Manually-verified live membership | `0` |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_MODEL_PRO` | LLM CLI provider/model | example defaults |
| `COMMUNITY_NAME` / `CORPUS_DESCRIPTION` / `GROUND_TRUTH_SUMMARY` | Context for synthesis prompt | generic |
| `REPORT_TITLE` / `REPORT_SUBJECT` / `REPORT_PERIOD` | Report front-matter | generic |

See [`docs/PIPELINE.md`](docs/PIPELINE.md) for the full list and usage.

## Project structure

```
src/parallax/
├── core/
│   ├── analyze.py               # main pipeline (parallax-analyze)
│   ├── languages.py             # language/region profile registry
│   ├── keywords.py              # keyword dictionaries — tune for your product
│   ├── crosstabs.py             # cross-tabulation helper (parallax-crosstabs)
│   ├── config.py                # YAML config loader (fact_schema, queries, etc.)
│   ├── diff.py                  # stats comparison tool (parallax-diff)
│   └── state.py                 # SQLite state store for --incremental
├── config/                      # YAML config files (override via PARALLAX_CONFIG_DIR)
│   ├── fact_schema.yaml         # Stream C extraction schema
│   ├── queries.yaml             # Stream B retrieval queries by language
│   ├── brand_patterns.yaml      # post_analysis brand audit patterns
│   ├── url_domains.yaml         # URL classification domain lists
│   └── canonical_schema.json    # JSON Schema for --platform canonical
├── streams/
│   ├── topics.py                # Stream A: LLM topic-tagging (parallax-topics)
│   ├── semantic_retrieval.py    # Stream B: embeddings + FAISS semantic search
│   ├── fact_extraction.py          # Stream C: structured LLM fact extraction (tolerant JSON)
│   ├── deterministic_analytics.py # Stream D: ground-truth-anchored analytics
│   ├── narrative_synthesis.py   # feeds all streams into one LLM synthesis call
│   ├── build_final_report.py    # assembles methodology + findings + recommendations
│   └── post_analysis.py         # brand audit, cost drill, CSV exports
└── templates/
    └── report-template.md       # report skeleton with {{stats.xxx}} placeholders
```

## Getting chat exports

| Platform | `--platform` | How to export |
|---|---|---|
| Discord | `discord` | [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter) → JSON |
| Telegram | `telegram` | Telegram Desktop → group → Export chat history → JSON |
| Lark/Feishu | `lark` | [@larksuite/cli](https://github.com/larksuite/cli) `im +chat-messages-list` |
| Slack | `slack` | Slack workspace → Settings → Export workspace data (zip or directory of JSONs) |
| CSV (generic) | `csv` | Any tool that produces a CSV with a `content` column (plus optional `author`, `timestamp`, `channel`) |
| Anything else | `canonical` | Match the [canonical JSON schema](src/parallax/config/canonical_schema.json) |

## Incremental analysis

Re-running `parallax-analyze` on an updated export normally processes everything from scratch. With `--incremental`, only new messages (by message ID) are processed, and results are merged into the existing `stats.json`:

```bash
# First run (full):
parallax-analyze --input export.json --platform discord --out ./out

# Subsequent runs (incremental):
parallax-analyze --input export_updated.json --platform discord --out ./out --incremental -v
```

A SQLite state store (`parallax_state.db` in the output dir) tracks which message IDs have been seen. Counter-type stats (providers, friction, features, etc.) are summed; user counts take the max (conservative, since the same user may appear in both runs).

## Comparing runs

Use `parallax-diff` to compare two `stats.json` files:

```bash
parallax-diff --old ./run1/stats.json --new ./run2/stats.json
# or JSON output:
parallax-diff --old ./run1/stats.json --new ./run2/stats.json --json
```

Shows KPI deltas (messages, users, questions, friction, answered rate), per-counter changes with new/gone/changed status, and percentage deltas.

## Privacy

- User IDs are SHA-256-hashed with a local salt before reaching any output file
- `--keep-names` is OFF by default; display names are `<redacted>`
- Salt is auto-generated with `secrets.token_hex(32)`, chmod `0600`, gitignored

## License

MIT — see [LICENSE](LICENSE).
