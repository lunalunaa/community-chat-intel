# Parallax test suite

Tests cover:
- `languages.py`: classification, script-ratio, stopword-ratio, all profiles
- `keywords.py`: compile, match, CJK vs ASCII, question patterns
- `analyze.py`: URL extraction/classification, hashing, language classification wrapper, question detection, min/max timestamps
- `crosstabs.py`: provider clusters, messaging buckets, pivot logic

Run: `pytest` (or `uv run pytest`)
