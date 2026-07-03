"""Integration test: synthetic export → full pipeline → assert stats shape."""

import json
from pathlib import Path

from parallax.core import analyze
from parallax.core import languages as lang


def _make_discord_export(messages_data: list[dict]) -> dict:
    """Build a minimal Discord export JSON."""
    return {
        "guild": {"name": "test-guild"},
        "channel": {"id": "1", "name": "general"},
        "messages": messages_data,
    }


def _make_messages(n: int = 20) -> list[dict]:
    """Generate n synthetic messages with varied content."""
    templates = [
        ("怎么安装这个？deepseek报错了", "2026-01-01T12:00:00+00:00"),
        ("I got an error with openai api key", "2026-01-01T13:00:00+00:00"),
        ("how to use skills memory cron", "2026-01-02T09:00:00+00:00"),
        ("this product is too expensive", "2026-01-03T14:00:00+00:00"),
        ("feishu adapter demand is high", "2026-01-04T10:00:00+00:00"),
        ("claude code is better than this", "2026-01-05T11:00:00+00:00"),
        ("can someone share an api key", "2026-01-06T15:00:00+00:00"),
        ("built a bot with skills and cron", "2026-01-07T16:00:00+00:00"),
        ("wsl docker install fails", "2026-01-08T08:00:00+00:00"),
        ("this is the official site right?", "2026-01-09T17:00:00+00:00"),
    ]
    msgs = []
    for i in range(n):
        content, ts = templates[i % len(templates)]
        msgs.append(
            {
                "id": str(i + 1),
                "author": {"id": f"u{i % 5}", "name": f"user_{i % 5}"},
                "timestamp": ts,
                "content": content,
                "reactions": [],
                "attachments": [],
            }
        )
    return msgs


def _run_on_discord_export(
    tmp_path: Path,
    messages: list[dict],
    target_language: str = "zh",
    region: str = "cn",
):
    """Helper: write export, load it, run pipeline, return (users_dict, stats_dict)."""
    export = _make_discord_export(messages)
    export_path = tmp_path / "export.json"
    export_path.write_text(json.dumps(export, ensure_ascii=False))

    salt_path = tmp_path / "salt.key"
    salt = analyze.ensure_salt(salt_path)
    msg_list = list(analyze.load_discord_export(export_path, salt))

    lang_profile = lang.get_language_profile(target_language)
    region_profile = lang.get_region_profile(region)
    assert region_profile is not None

    return analyze.run_pipeline(
        msg_list,
        language_profile=lang_profile,
        region_profile=region_profile,
        verbose=False,
    )


class TestPipelineEndToEnd:
    """Run the full parallax pipeline on synthetic data."""

    def test_pipeline_produces_valid_stats(self, tmp_path):
        users, stats = _run_on_discord_export(tmp_path, _make_messages(20))

        assert "metadata" in stats
        assert stats["metadata"]["total_messages"] == 20
        assert "channels" in stats["metadata"]
        assert "date_range" in stats["metadata"]
        assert stats["metadata"]["date_range"][0] is not None
        assert stats["metadata"]["date_range"][1] is not None
        assert stats["metadata"]["target_language"] == "zh"
        assert stats["metadata"]["region"] == "cn"

        assert "language_distribution" in stats
        assert "users" in stats
        assert stats["users"]["total"] == 5  # 5 unique users
        assert "retention" in stats
        assert "providers" in stats
        assert "competitors" in stats
        assert "messaging_platforms" in stats
        assert "features" in stats
        assert "friction_signals" in stats
        assert "urls" in stats
        assert "help_answered" in stats

    def test_pipeline_with_none_language(self, tmp_path):
        """--target-language none disables language classification."""
        users, stats = _run_on_discord_export(
            tmp_path, _make_messages(10), target_language="none", region="global"
        )

        # Every non-empty message should be "target" when language is disabled
        assert (
            stats["language_distribution"].get("target", 0)
            + stats["language_distribution"].get("unknown", 0)
            == 10
        )
        assert stats["metadata"]["target_language"] is None

    def test_pipeline_detects_providers(self, tmp_path):
        """Verify provider mentions are detected."""
        _, stats = _run_on_discord_export(tmp_path, _make_messages(20))

        assert "openai" in stats["providers"]
        # deepseek may or may not appear depending on language classification
        # of the message containing it — just assert at least 1 provider
        assert len(stats["providers"]) >= 1

    def test_pipeline_detects_friction(self, tmp_path):
        """Verify friction signals are detected."""
        _, stats = _run_on_discord_export(tmp_path, _make_messages(20))

        assert (
            "error_generic" in stats["friction_signals"]
            or "key_issue" in stats["friction_signals"]
        )

    def test_pipeline_detects_features(self, tmp_path):
        """Verify feature mentions are detected."""
        _, stats = _run_on_discord_export(tmp_path, _make_messages(20))

        assert "skills" in stats["features"]
        assert "cron" in stats["features"]

    def test_pipeline_detects_messaging(self, tmp_path):
        """Verify messaging platform mentions are detected."""
        _, stats = _run_on_discord_export(tmp_path, _make_messages(20))

        assert "feishu_lark" in stats["messaging_platforms"]

    def test_salt_is_generated(self, tmp_path):
        """Salt file should be auto-generated on first run."""
        export = _make_discord_export(_make_messages(5))
        export_path = tmp_path / "export.json"
        export_path.write_text(json.dumps(export, ensure_ascii=False))

        salt_path = tmp_path / "salt.key"
        assert not salt_path.exists()

        salt = analyze.ensure_salt(salt_path)

        assert salt_path.exists()
        assert len(salt.strip()) > 0

    def test_user_ids_are_hashed(self, tmp_path):
        """User IDs in the output should be hashed, not raw."""
        users_dict, stats = _run_on_discord_export(tmp_path, _make_messages(10))

        for uid in users_dict:
            # Hashed IDs are 16-char hex (no "u_" prefix in this version)
            assert len(uid) == 16 or uid == "unknown"
            # Should NOT contain the raw "u0", "u1" etc. from the export
            assert uid not in ("u0", "u1", "u2", "u3", "u4")
