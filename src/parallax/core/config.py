"""Config loader for parallax.

Loads YAML config files from PARALLAX_CONFIG_DIR env var (default: the
bundled defaults in src/parallax/config/). Override by setting the env var
to your own directory with matching filenames.

Config files:
  fact_schema.yaml     — Stream C extraction schema + prompt rules
  queries.yaml         — Stream B retrieval queries by language
  brand_patterns.yaml  — post_analysis.py brand audit regex patterns
  url_domains.yaml     — analyze.py URL classification domain lists
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config"


def _config_dir() -> Path:
    return Path(os.environ.get("PARALLAX_CONFIG_DIR", str(_DEFAULT_CONFIG_DIR)))


def _load_yaml(filename: str) -> dict[str, Any]:
    path = _config_dir() / filename
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    if yaml is None:
        raise ImportError(
            "PyYAML is required for config loading. Install with: pip install pyyaml"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if data is not None else {}


@lru_cache(maxsize=4)
def load_fact_schema() -> dict[str, Any]:
    """Load the fact extraction schema config."""
    return _load_yaml("fact_schema.yaml")


@lru_cache(maxsize=4)
def load_queries() -> dict[str, dict[str, str]]:
    """Load retrieval queries, keyed by language code."""
    return _load_yaml("queries.yaml")


@lru_cache(maxsize=4)
def load_brand_patterns() -> dict[str, str]:
    """Load brand audit regex patterns."""
    return _load_yaml("brand_patterns.yaml")


@lru_cache(maxsize=4)
def load_url_domains() -> dict[str, list[str]]:
    """Load URL classification domain lists."""
    return _load_yaml("url_domains.yaml")


def build_extraction_prompt(schema: dict[str, Any], language_name: str) -> str:
    """Build the LLM extraction prompt from the config schema."""
    intro = schema.get("prompt_intro", "").strip()
    rules = schema.get("prompt_rules", [])
    categories = schema.get("categories", [])

    # Build JSON schema example
    fields_lines = []
    for cat in categories:
        field = cat["field"]
        sub_fields = cat.get("fields", {})
        items = ", ".join(f'"{k}": {v}' for k, v in sub_fields.items())
        fields_lines.append(f'  "{field}": [{{{items}}}]')
    json_example = "{\n" + ",\n".join(fields_lines) + "\n}"

    # Build rules text
    rules_text = "\n".join(f"- {r}" for r in rules)

    return (
        f"You are analyzing a chunk of chat messages from a product's community chat "
        f"({language_name}-language, on a chat platform). {intro}\n\n"
        f"{json_example}\n\n"
        f"Rules:\n{rules_text}\n\n"
        f"MESSAGES:\n"
    )


def get_extraction_categories(schema: dict[str, Any]) -> list[str]:
    """Return the list of category field names from the schema."""
    return [c["field"] for c in schema.get("categories", [])]
