# Contributing to parallax

Thanks for your interest in contributing! This guide covers setup, development workflow, and standards.

## Quick start

```bash
# Fork & clone the repo, then:
cd parallax
uv sync --extra dev          # preferred (first install downloads ~1-2 GB)
# or:
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# Activate the venv once per session:
source .venv/bin/activate

# Verify everything works:
ruff check . && ruff format --check . && basedpyright && pytest tests/ -v
```

## Development workflow

1. **Fork** the repo on GitHub
2. **Create a branch**: `git checkout -b my-feature`
3. **Make changes** — follow the code style below
4. **Run all checks** before committing:
   ```bash
   ruff check .          # must pass with 0 errors
   ruff format .         # auto-format
   basedpyright          # must be 0 errors, 0 warnings
   pytest tests/ -v      # all tests must pass
   ```
5. **Commit** with a clear message (what + why)
6. **Push** and open a Pull Request

## Code style

- **Linter:** ruff (config in `ruff.toml`)
- **Type checker:** basedpyright, standard mode (`pyrightconfig.json`)
- **Target:** zero lint errors, zero type errors at all times
- **Imports:** `from __future__ import annotations` at the top of every module
- **Style:** match existing conventions in the file you're editing — no drive-by refactors

### Legacy stream scripts

Files in `src/parallax/streams/` (except `topics.py` and `generate_dashboard.py`) are
legacy one-shot scripts. They have per-file ruff ignores in `ruff.toml`. **Do not
refactor these for style** — only touch them if fixing a real bug.

## Testing

- **Framework:** pytest
- **Location:** `tests/`
- **Run:** `pytest tests/ -v`
- When adding a new feature, add tests for it
- When fixing a bug, add a regression test

## Architecture

See [AGENTS.md](AGENTS.md) for the full architecture overview, file reference, and
conventions. See [docs/PIPELINE.md](docs/PIPELINE.md) for the stream pipeline architecture.

## Configuration customization

- **Keywords:** Edit `src/parallax/core/keywords.py` for your community's terms
- **Category labels:** Edit `src/parallax/config/categories.yaml` for dashboard labels
- **Templates:** Ready-made keyword sets in `src/parallax/config/templates/`
- **Override dir:** Set `PARALLAX_CONFIG_DIR` to use your own config directory

## Privacy

- User IDs are always SHA-256-hashed. Never commit raw chat data, salt files, or `.env`
- `--keep-names` is OFF by default — display names are `<redacted>` in outputs
- Salt is auto-generated with `secrets.token_hex(32)`, chmod `0600`, gitignored

## Questions?

Open an [issue](https://github.com/lunalunaa/parallax/issues) — happy to help!
