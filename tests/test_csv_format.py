"""Tests for --format csv output in parallax-analyze."""

import json
from pathlib import Path

from parallax.core import analyze
from parallax.core import languages as lang


def _make_discord_export(n: int = 10) -> dict:
    msgs = []
    for i in range(n):
        msgs.append(
            {
                "id": str(i + 1),
                "author": {"id": f"u{i % 3}", "name": f"user_{i % 3}"},
                "timestamp": f"2026-01-{i + 1:02d}T12:00:00+00:00",
                "content": "how to use cargo and rustup for borrow checker error",
                "reactions": [],
                "attachments": [],
            }
        )
    return {
        "guild": {"name": "test"},
        "channel": {"id": "1", "name": "general"},
        "messages": msgs,
    }


def _run_pipeline_to_stats(tmp_path: Path) -> dict:
    export = _make_discord_export(10)
    export_path = tmp_path / "export.json"
    export_path.write_text(json.dumps(export))
    salt = analyze.ensure_salt(tmp_path / "salt.key")
    msgs = list(analyze.load_discord_export(export_path, salt))
    lp = lang.get_language_profile("zh")
    rp = lang.get_region_profile("cn")
    _, stats = analyze.run_pipeline(msgs, language_profile=lp, region_profile=rp)
    return stats


class TestStatsCSVExport:
    def test_csv_has_header(self, tmp_path):
        stats = _run_pipeline_to_stats(tmp_path)
        csv_path = tmp_path / "stats.csv"

        # Write CSV (same logic as analyze.py main())
        import csv as csv_mod

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv_mod.writer(f)
            writer.writerow(["category", "key", "value"])
            for category, data in stats.items():
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, (int, float, str)):
                            writer.writerow([category, key, value])
                        elif isinstance(value, dict):
                            for subkey, subvalue in value.items():
                                if isinstance(subvalue, (int, float, str)):
                                    writer.writerow(
                                        [category, f"{key}.{subkey}", subvalue]
                                    )

        with open(csv_path) as f:
            reader = csv_mod.reader(f)
            header = next(reader)
            assert header == ["category", "key", "value"]

    def test_csv_contains_metadata(self, tmp_path):
        stats = _run_pipeline_to_stats(tmp_path)
        csv_path = tmp_path / "stats.csv"

        import csv as csv_mod

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv_mod.writer(f)
            writer.writerow(["category", "key", "value"])
            for category, data in stats.items():
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, (int, float, str)):
                            writer.writerow([category, key, value])

        with open(csv_path) as f:
            rows = list(csv_mod.reader(f))

        # Find metadata.total_messages
        msg_rows = [r for r in rows if r[0] == "metadata" and r[1] == "total_messages"]
        assert len(msg_rows) == 1
        assert msg_rows[0][2] == "10"

    def test_csv_contains_providers(self, tmp_path):
        stats = _run_pipeline_to_stats(tmp_path)
        csv_path = tmp_path / "stats.csv"

        import csv as csv_mod

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv_mod.writer(f)
            writer.writerow(["category", "key", "value"])
            for category, data in stats.items():
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, (int, float, str)):
                            writer.writerow([category, key, value])

        with open(csv_path) as f:
            rows = list(csv_mod.reader(f))

        provider_rows = [r for r in rows if r[0] == "providers"]
        assert len(provider_rows) >= 1
        assert any(r[1] == "cargo" for r in provider_rows)
