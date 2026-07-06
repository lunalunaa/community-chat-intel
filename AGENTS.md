# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

**parallax** is a privacy-preserving chat-history analysis toolkit. It turns raw chat exports (Discord, Telegram, Lark, Slack, CSV, or canonical JSON) into structured community-intelligence reports. The pipeline combines NLP heuristics, local embeddings (BGE-M3 + FAISS), structured LLM fact extraction, deterministic analytics, and multi-model synthesis. User IDs are SHA-256-hashed by default; no raw quotes leak into outputs.

- **Package name:** `parallax`
- **Version:** 1.0.0
- **License:** MIT
- **Python:** >=3.10 (CI uses 3.12)
- **Repo:** github.com/lunalunaa/parallax

## Setup

```bash
uv sync --extra dev          # preferred
# or:
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
```

First install downloads ~1–2 GB (sentence-transformers / faiss-cpu / torch). This is expected.

Activate the venv once per session: `source .venv/bin/activate` — state persists across terminal calls.

## Commands

| Task | Command |
|------|---------|
| Lint | `uv run ruff check .` |
| Format check | `uv run ruff format --check .` |
| Type-check | `uv run basedpyright` (must be 0 errors) |
| Tests | `uv run pytest tests/ -v` |
| Build package | `uv build` |
| Run pipeline | `uv run parallax-analyze --input <export> --platform discord --out ./out -v` |
| Run stream script | `python -m parallax.streams.<name>` (no `main()` on most streams) |

## CI gates (all must pass)

Defined in `.github/workflows/ci.yml`. Four parallel jobs:

1. **Lint (ruff)** — `ruff check .` + `ruff format --check .`
2. **Type-check (basedpyright)** — standard mode, includes `src/` only
3. **Tests (pytest)** — `pytest tests/ -v` with `.[dev]` installed
4. **Build & verify** — console scripts respond to `--help`, smoke test on synthetic data, `uv build` produces sdist + wheel

CI uses `uv`, Python 3.12, no cache in parallel jobs. Setup-uv versions are pinned per-job.

## Code style

- **Linter:** ruff (config in `ruff.toml`)
- **Type checker:** basedpyright, standard mode (`pyrightconfig.json`)
- **Target:** zero lint errors, zero type errors at all times
- **Imports:** `from __future__ import annotations` at the top of every module
- **Style:** match existing conventions in the file you're editing — no drive-by refactors

### Legacy one-shot scripts

Files in `src/parallax/streams/` (except `topics.py` and `generate_dashboard.py`) are legacy one-shot scripts that ran once and produced their output. They have per-file ruff ignores in `ruff.toml` for structural rules (E402, E722, E741, F841, etc.). **Do not refactor these for style** — refactoring adds risk with zero benefit. Only touch them if fixing a real bug.

## Architecture

```
src/parallax/
├── core/                        # Main pipeline + utilities
│   ├── analyze.py               # parallax-analyze: main pipeline
│   ├── languages.py             # Language/region profile registry (13 langs, 7 regions)
│   ├── keywords.py              # Keyword dictionaries — customize for your community
│   ├── crosstabs.py             # parallax-crosstabs: cross-tabulation helper
│   ├── config.py                # YAML config loader (PARALLAX_CONFIG_DIR)
│   ├── diff.py                  # parallax-diff: stats comparison tool
│   ├── init.py                  # parallax-init: project scaffolder
│   └── state.py                 # SQLite state store for --incremental
├── config/                      # YAML/JSON config (override via PARALLAX_CONFIG_DIR)
│   ├── fact_schema.yaml         # Stream C extraction schema
│   ├── queries.yaml             # Stream B retrieval queries by language
│   ├── brand_patterns.yaml      # post_analysis brand audit patterns
│   ├── url_domains.yaml         # URL classification domain lists
│   ├── canonical_schema.json    # JSON Schema for --platform canonical
│   └── templates/               # Ready-made keyword sets (AI product, gaming, programming)
├── streams/                     # 4-stream deep-analysis pipeline
│   ├── topics.py                # Stream A: LLM topic-tagging (parallax-topics)
│   ├── semantic_retrieval.py    # Stream B: embeddings + FAISS semantic search
│   ├── fact_extraction.py       # Stream C: structured LLM fact extraction
│   ├── deterministic_analytics.py # Stream D: ground-truth-anchored analytics (no LLM)
│   ├── narrative_synthesis.py   # Feeds all streams into one LLM synthesis call
│   ├── build_final_report.py    # Assembles methodology + findings + recommendations
│   ├── post_analysis.py         # Brand audit, cost drill, CSV exports
│   └── generate_dashboard.py    # Self-contained interactive HTML dashboard
└── templates/
    └── report-template.md       # Report skeleton with {{stats.xxx}} placeholders
```

### Console scripts (5)

| Script | Module | Has `main()`? |
|--------|--------|---------------|
| `parallax-analyze` | `parallax.core.analyze` | Yes |
| `parallax-topics` | `parallax.streams.topics` | Yes |
| `parallax-crosstabs` | `parallax.core.crosstabs` | Yes |
| `parallax-diff` | `parallax.core.diff` | Yes |
| `parallax-init` | `parallax.core.init` | Yes |

Other stream scripts are one-shot modules — run with `python -m parallax.streams.<name>`.

### Pipeline stages (analyze.py)

1. Load adapter (platform-specific → canonical schema)
2. Language classify each message (per `--target-language` profile)
3. Build per-user profiles
4. Keyword extraction (providers, competitors, messaging, features, friction, shadow, acquisition)
5. Question detection (per language profile) + reply-graph for help-answered-rate
6. Retention cohort assignment
7. Aggregate stats
8. Write outputs (stats.json, users.json, report.md)

## Configuration

- **Config dir:** `src/parallax/config/` (override via `PARALLAX_CONFIG_DIR` env var)
- **Keywords:** `src/parallax/core/keywords.py` — Rust community example by default; customize for your community. Templates in `config/templates/`.
- **Language/region:** `src/parallax/core/languages.py` — add entries to support new markets. Defaults: `--target-language none`, `--region global`, TZ=UTC.
- **Stream scripts** read from environment variables (`CHAT_JSONL`, `OUT_DIR`, `SALT_FILE`, `LLM_PROVIDER`, etc.) — no hardcoded paths. See `docs/PIPELINE.md` for the full list.

## Testing

- **Framework:** pytest
- **Location:** `tests/` (11 test files)
- **Run:** `uv run pytest tests/ -v`
- Tests cover: adapters, analyze pipeline, config loading, crosstabs, CSV format, incremental analysis, init scaffolder, integration, keywords, languages
- Smoke test in CI uses synthetic Discord export with 2 messages

## Dashboard design standards

The dashboard (`generate_dashboard.py`) must meet high visual standards — inspired by magicui.design and performative-ui. Expected design elements:

- **Dark theme** with gradient fills (not flat colors)
- **Glow effects** per data category
- **Number ticker** animations on KPI cards
- **Bento grid** layout
- **SVG charts** (not CSS divs) for bar lists and trend charts
- **Animated node graph** background
- **Glass cards** with blur fade-in
- **Auto-generated insights** summary
- **Generic labels** (e.g. "Top mentions", not "Provider mentions")
- **Self-contained** — single HTML file, no external dependencies, works offline

A functional but flat dashboard will be rejected.

## Conventions

- **Neutral terminology:** Use generic terms ("target-language", "locale-specific", "region") — never name a specific locale/community in defaults or generic code. Defaults: `target-language=none`, `region=global`, TZ=UTC.
- **Versioning:** Semantic versioning. Don't over-inflate version numbers. Current: 1.0.0.
- **Commit history:** Keep it clean. Rewrite embarrassing commit messages before pushing.
- **No PyPI publishing:** The PyPI publish workflow was intentionally removed. Do not re-add it.
- **Docs:** Update docs in the same commit as code changes.
- **Privacy:** User IDs are always SHA-256-hashed. `--keep-names` is OFF by default. Never commit raw chat data, salt files, or `.env`.

## Key files to know

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, dependencies, console scripts |
| `ruff.toml` | Lint rules + per-file ignores for legacy scripts |
| `pyrightconfig.json` | Type-checking config (standard mode, venv at `.venv`) |
| `docs/PIPELINE.md` | Full pipeline architecture, per-stream I/O, cost breakdown |
| `docs/DASHBOARD.md` | Dashboard feature docs |
| `examples/quickstart.ipynb` | End-to-end walkthrough notebook |
| `CHANGELOG.md` | Version history (6 phases) |
| `.gitignore` | Ignores `out/`, `data/`, `*.key`, `.env`, caches |

## Privacy & security

- **Never** commit: raw chat exports (`data/`, `*.jsonl`), salt files (`*.key`), `.env` files
- User IDs are SHA-256-hashed with a local salt before any output
- Display names are `<redacted>` by default; `--keep-names` must be explicitly passed
- Salt is auto-generated with `secrets.token_hex(32)`, chmod `0600`, gitignored

## What NOT to do

- Don't add a PyPI publish workflow — it was intentionally removed
- Don't refactor legacy one-shot stream scripts for style (see ruff.toml ignores)
- Don't hardcode locale-specific terms in generic code — use the config/registry pattern
- Don't commit raw chat data or secrets
- Don't over-inflate version numbers
- Don't add CSS div charts to the dashboard — use SVG
- Don't use flat colors in the dashboard — use gradients + glow
