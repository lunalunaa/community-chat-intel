# community-chat-intel

**A privacy-preserving toolkit for turning raw chat exports (Discord / Telegram / Feishu-Lark / any JSON export) into structured community-intelligence reports — combining classic NLP heuristics, local embeddings, structured LLM extraction, deterministic analytics, and multi-model synthesis into a single reproducible pipeline.**

Built to answer a real question — *"how does our non-English-speaking user community actually use our product?"* — without running an intrusive survey. The pipeline extracts the same research signals a poll would have produced (usage patterns, install friction, provider/platform preferences, brand confusion, feature requests) passively from existing chat history, with hashed user IDs and no raw-quote leakage by default.

**Not limited to Chinese.** Pick any target language/region with `--target-language` / `--region` (see [`src/chatintel/core/languages.py`](src/chatintel/core/languages.py)) — Japanese/Japan, Korean/Korea, Russian/Russia-CIS, Spanish/LatAm, Arabic/MENA, or add your own profile. `--target-language none` disables the language-cohort split entirely for already-monolingual exports. The pipeline was originally built and tested end-to-end against a real ~3,100-member Chinese-language community chat — kept as the default and as one fully-worked example (with real, illustrative numbers) in [`docs/PIPELINE.md`](docs/PIPELINE.md) — but every language/region-specific behavior (message-language detection, question-marker patterns, shadow-community platforms, timezone-proxy buckets, regional provider clustering) is now driven by a swappable profile, not hardcoded.

## Why this exists / what it demonstrates

- **Packaged as a proper Python project** — `src/`-layout package installable with `pip install -e .` or `uv sync` / `uv pip install -e .`; ships `chatintel-analyze`, `chatintel-topics`, `chatintel-crosstabs` console scripts so you don't need to know the internal file layout to run it.
- **Language/region-agnostic core, one worked example** — `languages.py` centralizes everything that differs by target market: script-ratio or stopword-ratio language detection (CJK-family scripts, Cyrillic, Arabic, Latin-script languages via a stopword heuristic), per-language question-marker regexes, per-region shadow-community platform lists, per-region timezone-proxy buckets, and per-region "which providers count as regional" clustering. Add a new market by adding one `LanguageProfile` + one `RegionProfile` entry — no pipeline code changes required.
- **Multi-stream analysis architecture** — four independent analysis techniques (broad LLM topic tagging, local-embedding semantic retrieval + FAISS, structured LLM fact extraction with tolerant JSON retry, and pure-Python deterministic analytics) run in parallel over the same corpus and get reconciled by a final synthesis pass. Each stream compensates for another's blind spots — see [`docs/PIPELINE.md`](docs/PIPELINE.md) for the full rationale.
- **Ground-truth anchoring** — chat platforms that don't log "member left" events (Feishu/Lark, and effectively most groups without admin logs) make join-event counts systematically overstate current membership. The pipeline pins retention/engagement denominators to a manually-verified live membership count instead of trusting derived numbers.
- **Zero-dependency LLM orchestration** — every LLM call shells out to a locally-configured LLM CLI (`hermes chat -q ...` by default), so there are no API keys hardcoded anywhere in this codebase and switching providers is a one-flag change (`LLM_PROVIDER` / `LLM_MODEL` env vars). Swap the `cmd` list in each stream script if you use a different CLI.
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
        (semantic_    (fact_        (deterministic_
         retrieval.py)  extraction.py) analytics.py)
                 │             │             │
                 └─────────────┼─────────────┘
                               │
                 narrative_synthesis.py
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

**With uv (recommended):**

```bash
git clone <this repo>
cd community-chat-intel
uv sync          # creates .venv, installs deps + this package, writes uv.lock
source .venv/bin/activate
```

**With pip:**

```bash
git clone <this repo>
cd community-chat-intel
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Either way you end up with the `chatintel-analyze` / `chatintel-topics` / `chatintel-crosstabs` console scripts on `PATH`:

```bash
# 1. Get a chat export (Discord/Telegram/Lark — see "Getting chat exports" below)
#    Result: e.g. ~/Downloads/discord_export.json

# 2. Core keyword-analysis pipeline (seconds for small exports)
#    Defaults to --target-language zh --region cn for backward compatibility;
#    pick your own market, e.g. Japanese/Japan:
chatintel-analyze --input ~/Downloads/discord_export.json --platform discord \
    --target-language ja --region jp --out ./out -v

# 3. (Optional) LLM topic tagging — shells out to your configured `hermes` CLI
chatintel-topics --input-chat ~/Downloads/discord_export.json --platform discord \
    --target-language ja --out ./out/topics.json --limit 200

# 4. (Optional) Cross-tabulations
chatintel-crosstabs --users-json ./out/users.json --region jp --out ./out/crosstabs.json

# 5. Review ./out/report.md, ./out/stats.json, ./out/crosstabs.md
```

The remaining 4-stream deep-analysis scripts (`semantic_retrieval.py`, `fact_extraction.py`, `fact_extraction_retry.py`, `deterministic_analytics.py`, `narrative_synthesis.py`, `build_final_report.py`, `post_analysis.py`) are one-shot scripts, not console commands — run them as modules from an activated venv, e.g.:

```bash
python -m chatintel.streams.deterministic_analytics
```

For the full pipeline (semantic retrieval, structured fact extraction, deterministic analytics, cross-stream synthesis, final report with recommendations), see [`docs/PIPELINE.md`](docs/PIPELINE.md) — it documents exact commands, environment variables, and a real cost/runtime breakdown.

## Language / region support

`--target-language` and `--region` are accepted by `chatintel-analyze`, `chatintel-topics`, and `chatintel-crosstabs`. See [`src/chatintel/core/languages.py`](src/chatintel/core/languages.py) for the full registry and to add your own:

| `--target-language` | Language | Detection method |
|---|---|---|
| `zh` (default) | Chinese | CJK-ideograph script ratio |
| `ja` | Japanese | Hiragana/Katakana + shared CJK ideograph script ratio |
| `ko` | Korean | Hangul script ratio |
| `ru` | Russian | Cyrillic script ratio |
| `ar` | Arabic | Arabic script ratio |
| `he` | Hebrew | Hebrew script ratio |
| `th` | Thai | Thai script ratio |
| `vi` | Vietnamese | Vietnamese-diacritic script ratio |
| `es`, `fr`, `de`, `pt`, `id` | Spanish, French, German, Portuguese, Indonesian | Stopword-frequency ratio (lower precision than script-ratio languages — spot-check a sample) |
| `none` | — | Disables language classification; every message counts as target (for already-monolingual exports) |

| `--region` | Region | Shadow-community platforms | Timezone-proxy buckets |
|---|---|---|---|
| `cn` (default) | Greater China | Zhihu, WeChat OA/groups, QQ groups, Bilibili, Xiaohongshu, Juejin, CSDN, ... | mainland/NA/EU evening |
| `jp` | Japan | note.com, Qiita, Zenn, X, 5ch, ... | JST/NA/EU evening |
| `kr` | Korea | Naver Blog, Velog, Disquiet, OKKY, KakaoTalk open chat, ... | KST/NA/EU evening |
| `ru` | Russia/CIS | VK, Habr, Telegram channels, ... | MSK/EU/NA evening |
| `latam` | Latin America | Reddit, YouTube, Discord, WhatsApp groups, ... | LatAm/NA/EU evening |
| `mena` | Middle East/North Africa | Reddit, Telegram channels, YouTube, ... | Gulf/EU/NA evening |
| `global` | Global/English-default | Reddit, Hacker News, LinkedIn, Product Hunt, ... | NA/EU/APAC evening |

Adding a new language or region is a matter of adding one `LanguageProfile` / `RegionProfile` entry to `src/chatintel/core/languages.py` — no changes needed elsewhere in the pipeline.

## Adapting for your own community

All stream scripts (`semantic_retrieval.py`, `fact_extraction.py`, `fact_extraction_retry.py`, `deterministic_analytics.py`, `post_analysis.py`, `narrative_synthesis.py`, `build_final_report.py`) read their configuration from environment variables instead of hardcoded paths, so you can point the whole pipeline at your own dataset without editing code:

| Variable | Purpose | Default |
|---|---|---|
| `CHAT_JSONL` | Path to the raw NDJSON export | `./data/pages.jsonl` |
| `OUT_DIR` | Output directory for all streams | `./out` |
| `SALT_FILE` | User-ID hashing salt (auto-generate with `chatintel-analyze` on first run) | `./user_hash_salt.key` |
| `TARGET_LANGUAGE` | Which `QUERIES_BY_LANGUAGE` set `semantic_retrieval.py` runs, and how the LLM prompts in `semantic_retrieval.py`/`fact_extraction.py`/`fact_extraction_retry.py` describe the corpus's language | `zh` (also ships an `en` example set; add your own entry for other languages) |
| `TS_UTC_OFFSET_HOURS` | UTC offset (hours) used to parse `"YYYY-MM-DD HH:MM"`-style display timestamps that lack a timezone marker, in `semantic_retrieval.py`/`fact_extraction.py`/`fact_extraction_retry.py`/`deterministic_analytics.py` | `8` (China Standard Time, for backward compatibility with the original Feishu-export example; set `0` for UTC, `9` for Japan/Korea, etc.) |
| `GROUND_TRUTH_HUMANS` / `GROUND_TRUTH_BOTS` | Manually-verified live membership (`deterministic_analytics.py` denominator) | `0` (must be set for meaningful output) |
| `GROUND_TRUTH_SOURCE` | Free-text provenance note for the ground-truth numbers | `"platform admin UI, manually verified"` |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_MODEL_PRO` | Which provider/model your LLM CLI should use | `nous` / `xiaomi/mimo-v2.5` / `xiaomi/mimo-v2.5-pro` (example — use whatever you have configured) |
| `COMMUNITY_NAME`, `CORPUS_DESCRIPTION`, `GROUND_TRUTH_SUMMARY` | Free-text context injected into the narrative-synthesis prompt | generic examples |
| `SURVEY_SUBJECT`, `STRUCTURAL_CONTEXT`, `RECOMMENDATION_FOCUS_AREAS` | Free-text context injected into the recommendations-generation prompt | generic placeholders |
| `REPORT_TITLE`, `REPORT_SUBJECT`, `REPORT_PERIOD`, `REPORT_CLASSIFICATION` | Front-matter for the final assembled report | generic placeholders |

## Files

```
pyproject.toml                          # package metadata, console-script entry points
uv.lock                                 # pinned dependency lockfile (uv)
ruff.toml                               # lint config
requirements.txt                        # -> "pip install -e ." (kept for tools that expect it)
src/chatintel/
├── core/
│   ├── analyze.py                      # main pipeline (chatintel-analyze) — adapters, language
│   │                                    #   classification, keyword extraction, stats, redaction
│   ├── languages.py                    # language/region profile registry (script-ratio &
│   │                                    #   stopword-ratio detection, question markers,
│   │                                    #   shadow-community platforms, timezone buckets)
│   ├── keywords.py                     # keyword dictionaries — tune for your own product/ecosystem
│   └── crosstabs.py                    # cross-tabulation helper (chatintel-crosstabs)
├── streams/
│   ├── topics.py                        # Stream A: LLM topic-tagging (chatintel-topics)
│   ├── semantic_retrieval.py            # Stream B: local embeddings + FAISS semantic search
│   ├── fact_extraction.py               # Stream C: structured LLM fact extraction
│   ├── fact_extraction_retry.py         # Stream C: tolerant-JSON retry pass
│   ├── deterministic_analytics.py       # Stream D: ground-truth-anchored deterministic analytics
│   ├── narrative_synthesis.py           # feeds all four streams into one LLM synthesis call
│   ├── build_final_report.py            # assembles methodology + findings + recommendations
│   └── post_analysis.py                 # brand/impersonator audit, cost-complaint drill, CSV exports
└── templates/
    └── report-template.md              # report skeleton with {{stats.xxx}} placeholders

plan.md                                 # research methodology write-up (full worked example)
docs/PIPELINE.md                        # deep architecture doc for the 4-stream pipeline
docs/DASHBOARD.md                       # usage guide for the companion HTML dashboard
```

The stream scripts under `streams/` (other than `topics.py`) are one-shot scripts (module-level code, no `main()`) — run them with `python -m chatintel.streams.<name>`, not as console commands.

## Getting chat exports

- **Discord** — [`DiscordChatExporter`](https://github.com/Tyrrrz/DiscordChatExporter) (GUI/CLI/Docker)
- **Telegram** — Telegram Desktop → group → **Export chat history** → JSON
- **Lark/Feishu** — [`@larksuite/cli`](https://github.com/larksuite/cli), paginating `GET /open-apis/im/v1/messages`
- **Anything else** — write a JSON file matching the canonical schema (documented at the top of `chatintel-analyze --help`, source in `src/chatintel/core/analyze.py`) and use `--platform canonical`

## Privacy & ethics guardrails (enforced by the pipeline)

1. All `author_id` values are SHA-256-hashed with a local salt; raw platform user IDs never appear in `stats.json`.
2. `--keep-names` is default-OFF; display names are replaced with `<redacted>` in `users.json`.
3. The salt file is generated with `secrets.token_hex(32)` and chmod'd `0600` — never commit it, never share it.
4. Direct message quotes should be paraphrased before appearing in any shared report.

## Known limitations

Language classification is heuristic — script-ratio based for languages with a dedicated Unicode block (Chinese, Japanese, Korean, Russian, Arabic, Hebrew, Thai, Vietnamese), stopword-frequency based for Latin-script languages (Spanish, French, German, Portuguese, Indonesian) with correspondingly lower precision; question-detection is regex-based per language (English patterns always included as a fallback); reply-chain structure is platform-dependent; LLM extraction has a small (~1-2%) cross-field bleed rate; short export windows make retention metrics unreliable; regional-provider clustering and shadow-community platform lists in `src/chatintel/core/languages.py` are illustrative starting points for each region, not exhaustive — extend them for your own market. Full discussion in `docs/PIPELINE.md` §4 (Limitations & Caveats template inside `build_final_report.py`).

## License

MIT — see [LICENSE](LICENSE).
