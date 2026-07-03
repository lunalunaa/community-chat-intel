# Changelog

All notable changes to parallax are documented here.

## [Unreleased]

### Phase 6 — Polish for 1.0

- Added `parallax init` command to scaffold a new project directory with
  config files, salt file, .gitignore, and a project-specific README
- Added example Jupyter notebook walkthrough
- Added CHANGELOG.md

## [0.5.0] — 2026-07-03

### Phase 5 — Incremental analysis

- Added `parallax-analyze --incremental` flag: only processes new messages
  and merges results into existing stats.json via SQLite state store
- Added `parallax-diff` console script: compares two stats.json files,
  shows KPI deltas, per-counter changes, percentage deltas (text + JSON)
- New modules: `core/state.py` (SQLite state store), `core/diff.py`
- 172 tests pass

### Phase 4 — Broaden platform support

- Added Slack adapter (`--platform slack`): single JSON, directory, or zip
- Added generic CSV adapter (`--platform csv`): case-insensitive column aliases
- Added canonical JSON Schema file (`config/canonical_schema.json`)
- 6 platforms total: Discord, Telegram, Lark/Feishu, Slack, CSV, canonical
- 154 tests pass

## [0.4.0] — 2026-07-03

### Phase 3 — Interactive dashboard

- Rewrote `generate_dashboard.py` from static HTML to full interactive dashboard
- Filter controls: run selector, cohort toggle (All / Target-lang), view toggle
- Drill-down: click any bar to see matching messages (timestamp, sender, content)
- Trend view: pass multiple `--stats` files to compare runs over time
- Per-bar delta indicators (+N / -N) and KPI delta badges (↑ 12% vs prev)
- Chat format auto-detection: Discord JSON, Telegram JSON, NDJSON

### Phase 2 — Config-driven pipeline

- Moved 4 hardcoded config blocks to YAML files:
  - `config/fact_schema.yaml` (Stream C extraction schema)
  - `config/queries.yaml` (Stream B retrieval queries by language)
  - `config/brand_patterns.yaml` (post_analysis brand audit patterns)
  - `config/url_domains.yaml` (URL classification domain lists)
- New `core/config.py` module with `PARALLAX_CONFIG_DIR` env var override
- pyyaml added as runtime dependency
- 137 tests pass

## [0.3.0] — 2026-07-03

### Phase 1 — Test coverage

- Added test suite: 120 tests across 5 files
  - `test_languages.py` (31 tests): script-ratio, stopword-ratio, classification
  - `test_keywords.py` (24 tests): compile, match, CJK vs ASCII, question patterns
  - `test_analyze.py` (22 tests): hashing, URL classification, question detection,
    UserProfile.language_primary(), timestamp helpers, salt generation
  - `test_crosstabs.py` (12 tests): provider clusters, messaging buckets, retention
  - `test_integration.py` (8 tests): full pipeline end-to-end on synthetic Discord data
- Added pytest + pytest-cov to dev extras
- CI: added 'test' job (4 parallel jobs: lint, type-check, test, build)

### Pre-1.0 work

- Renamed project from `community-chat-intel` / `chatintel` to `parallax`
- Comprehensive decoupling from original use case (zero locale-specific coupling)
- Multi-language / multi-region support via `languages.py` (13 languages, 7 regions)
- Installable `src/parallax/` package with console-script entry points
- `uv.lock` committed for reproducibility
- CI workflow with lint (ruff), type-check (basedpyright), build & verify
- Dashboard generator (self-contained HTML, dark theme, bar-list visualizations)
- Renamed stream files to self-descriptive names
- Env-var-driven config (`CHAT_JSONL`, `OUT_DIR`, `TARGET_LANGUAGE`, etc.)
- Fixed basedpyright type-checking issues (standard mode, 0/0/0)
- Fixed Jupyter kernel setup for editors (Zed/VS Code)
- Cleaned commit history (no internal references in messages)
