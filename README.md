# community-chat-intel

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/Code%20style-ruff-261230.svg)](https://docs.astral.sh/ruff/)
[![Type checker: basedpyright](https://img.shields.io/badge/Type%20checker-basedpyright-orange.svg)](https://docs.basedpyright.com/)
[![Package manager: uv](https://img.shields.io/badge/uv-managed-de4c4a.svg)](https://docs.astral.sh/uv/)
[![CI](https://github.com/lunalunaa/community-chat-intel/actions/workflows/ci.yml/badge.svg)](https://github.com/lunalunaa/community-chat-intel/actions/workflows/ci.yml)

Turn raw chat exports (Discord / Telegram / Lark / any JSON) into structured community-intelligence reports — passively, without running a survey. Combines NLP heuristics, local embeddings (BGE-M3 + FAISS), structured LLM fact extraction, deterministic analytics, and multi-model synthesis into one reproducible pipeline. User IDs are SHA-256-hashed by default; no raw quotes leak into outputs.

Multi-language and multi-region out of the box — pick your target market with `--target-language` / `--region`, or add your own `LanguageProfile` + `RegionProfile`. Originally built and tested against a real ~3,100-member Chinese-language community; now generalized to 13 languages and 7 regions.

---

## Quick start

```bash
git clone https://github.com/lunalunaa/community-chat-intel.git
cd community-chat-intel

# Install (pick one):
uv sync --extra dev          # uv (recommended)
# — or —
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# Run:
chatintel-analyze --input ~/Downloads/discord_export.json --platform discord \
    --target-language ja --region jp --out ./out -v

# Optional: LLM topic tagging + cross-tabulations
chatintel-topics --input-chat ~/Downloads/discord_export.json --platform discord \
    --target-language ja --out ./out/topics.json
chatintel-crosstabs --users-json ./out/users.json --region jp --out ./out/crosstabs.json
```

> **First install is slow** (~1–2 GB for `sentence-transformers` / `faiss-cpu` / `torch`). This is expected.

<details>
<summary><b>Editor / Jupyter kernel setup (Zed, VS Code, JupyterLab)</b></summary>

This repo ships a `pyrightconfig.json` pointing at `.venv`. If your editor shows "missing import" errors or `Kernel error: No module named ipykernel_launcher`, it's using the wrong interpreter. Fix:

```bash
pip install -e ".[dev]"   # or: uv pip install -e ".[dev]"
python -m ipykernel install --user --name=chatintel --display-name="chatintel (.venv)"
```

Then select **"chatintel (.venv)"** in your editor's kernel/interpreter picker. Verify with `basedpyright .` (should report 0 errors).

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
python -m chatintel.streams.semantic_retrieval
python -m chatintel.streams.fact_extraction
python -m chatintel.streams.deterministic_analytics
python -m chatintel.streams.narrative_synthesis
python -m chatintel.streams.build_final_report
python -m chatintel.streams.post_analysis
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

Add your own market by adding one entry to [`src/chatintel/core/languages.py`](src/chatintel/core/languages.py) — no code changes elsewhere.

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
src/chatintel/
├── core/
│   ├── analyze.py               # main pipeline (chatintel-analyze)
│   ├── languages.py             # language/region profile registry
│   ├── keywords.py              # keyword dictionaries — tune for your product
│   └── crosstabs.py             # cross-tabulation helper (chatintel-crosstabs)
├── streams/
│   ├── topics.py                # Stream A: LLM topic-tagging (chatintel-topics)
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

- **Discord** — [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter)
- **Telegram** — Telegram Desktop → group → Export chat history → JSON
- **Lark/Feishu** — [@larksuite/cli](https://github.com/larksuite/cli)
- **Anything else** — match the canonical schema (`chatintel-analyze --help`) and use `--platform canonical`

## Privacy

- User IDs are SHA-256-hashed with a local salt before reaching any output file
- `--keep-names` is OFF by default; display names are `<redacted>`
- Salt is auto-generated with `secrets.token_hex(32)`, chmod `0600`, gitignored

## License

MIT — see [LICENSE](LICENSE).
