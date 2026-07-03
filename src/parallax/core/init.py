#!/usr/bin/env python3
"""Scaffold a new parallax project directory.

Usage:
    parallax init my-project
    parallax init my-project --platform slack --language en --region global

Creates a directory with:
  - config/          (copy of the bundled YAML config files — edit these)
  - data/            (place your chat export here)
  - out/             (pipeline outputs go here)
  - user_hash_salt.key  (auto-generated salt for user-ID hashing)
  - .gitignore       (ignores data/, out/, *.key, *.db)
  - README.md        (project-specific quickstart with your settings)
"""

import argparse
import shutil
import sys
from pathlib import Path


def init_project(
    name: str, platform: str = "discord", language: str = "zh", region: str = "cn"
) -> Path:
    """Create a scaffolded parallax project directory.

    Args:
        name: Directory name (or path) to create
        platform: Default platform to use in the generated README
        language: Default target language
        region: Default region

    Returns: Path to the created project directory
    """
    project_dir = Path(name)
    if project_dir.exists():
        print(f"[error] directory '{project_dir}' already exists", file=sys.stderr)
        sys.exit(1)

    project_dir.mkdir(parents=True)

    # Copy config files from the bundled package
    from parallax.core.config import _DEFAULT_CONFIG_DIR

    config_dest = project_dir / "config"
    config_dest.mkdir()
    for f in _DEFAULT_CONFIG_DIR.iterdir():
        if f.suffix in (".yaml", ".json"):
            shutil.copy2(f, config_dest / f.name)
    print(
        f"[init] copied {len(list(config_dest.iterdir()))} config files to {config_dest}/"
    )

    # Create data/ and out/ directories
    (project_dir / "data").mkdir()
    (project_dir / "data" / ".gitkeep").write_text("")
    (project_dir / "out").mkdir()
    (project_dir / "out" / ".gitkeep").write_text("")
    print("[init] created data/ and out/ directories")

    # Generate salt file
    import secrets

    salt = secrets.token_hex(32)
    salt_path = project_dir / "user_hash_salt.key"
    salt_path.write_text(salt)
    salt_path.chmod(0o600)
    print(f"[init] generated salt file: {salt_path}")

    # Generate .gitignore
    gitignore = """\
# Data & outputs (never commit real chat data)
data/*
!data/.gitkeep
out/*
!out/.gitkeep

# Secrets
*.key
*.db
*.sqlite3

# Python
__pycache__/
*.egg-info/
.venv/
"""
    (project_dir / ".gitignore").write_text(gitignore)
    print("[init] created .gitignore")

    # Generate project README
    readme = f"""# {project_dir.name}

Community chat analysis project powered by [parallax](https://github.com/lunalunaa/parallax).

## Quick start

```bash
# 1. Place your chat export in data/
#    (Discord: DiscordChatExporter → JSON; Slack: export zip; etc.)

# 2. Run the core pipeline
parallax-analyze \\
    --input data/export.json \\
    --platform {platform} \\
    --out out/ \\
    --target-language {language} \\
    --region {region} \\
    --salt-file user_hash_salt.key \\
    -v

# 3. Generate a dashboard
python -m parallax.streams.generate_dashboard \\
    --stats out/stats.json \\
    --users out/users.json \\
    --chat data/export.json \\
    --out out/dashboard.html

# 4. (Optional) Cross-tabulation
parallax-crosstabs --users-json out/users.json --region {region} --out out/crosstabs.json

# 5. (Optional) Compare runs
parallax-diff --old out/stats_prev.json --new out/stats.json
```

## Config

Edit `config/` YAML files to customize for your community:
- `fact_schema.yaml` — what facts to extract (Stream C)
- `queries.yaml` — semantic retrieval queries (Stream B)
- `brand_patterns.yaml` — brand/impersonator regex patterns
- `url_domains.yaml` — URL classification domain lists

Set `PARALLAX_CONFIG_DIR=config/` to use your custom config (default: the
bundled package config).

## Incremental analysis

```bash
parallax-analyze --input data/export_updated.json --platform {platform} \\
    --out out/ --salt-file user_hash_salt.key --incremental -v
```
"""
    (project_dir / "README.md").write_text(readme)
    print("[init] created README.md")

    print(f"\n[done] Project '{project_dir.name}' created at {project_dir}/")
    print(
        f"  Next: place your chat export in {project_dir}/data/ and run parallax-analyze"
    )
    return project_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold a new parallax project directory with config files and templates."
    )
    parser.add_argument("name", help="Directory name (or path) to create")
    parser.add_argument(
        "--platform",
        default="discord",
        choices=["discord", "telegram", "lark", "slack", "csv", "canonical"],
        help="Default platform for the generated README (default: discord)",
    )
    parser.add_argument(
        "--language",
        default="zh",
        help="Default target language code (default: zh)",
    )
    parser.add_argument(
        "--region",
        default="cn",
        help="Default region code (default: cn)",
    )
    args = parser.parse_args()

    init_project(args.name, args.platform, args.language, args.region)
    return 0


if __name__ == "__main__":
    sys.exit(main())
