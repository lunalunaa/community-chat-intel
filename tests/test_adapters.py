"""Tests for platform adapters (Slack, CSV, canonical schema validation)."""

import csv
import json
import zipfile
from pathlib import Path


from parallax.core import analyze


def _make_slack_messages(n: int = 5) -> list[dict]:
    msgs = []
    for i in range(n):
        msgs.append(
            {
                "type": "message",
                "user": f"U{i:05d}",
                "ts": f"1704067200.{i:06d}",  # 2024-01-01T00:00:00Z + offset
                "text": f"hello world message {i}",
                "reactions": [{"name": "thumbsup", "count": 1, "users": ["U99999"]}],
                "files": [],
            }
        )
    return msgs


class TestSlackAdapter:
    def test_single_channel_json(self, tmp_path):
        msgs = _make_slack_messages(5)
        path = tmp_path / "general.json"
        path.write_text(json.dumps(msgs))

        salt = "test-salt"
        results = list(analyze.load_slack_export(path, salt))

        assert len(results) == 5
        assert results[0].platform == "slack"
        assert results[0].channel == "general"
        assert results[0].content == "hello world message 0"
        assert results[0].author_id != "U00000"  # should be hashed

    def test_directory_of_channels(self, tmp_path):
        dir_path = tmp_path / "slack-export"
        dir_path.mkdir()
        (dir_path / "general.json").write_text(json.dumps(_make_slack_messages(3)))
        (dir_path / "random.json").write_text(json.dumps(_make_slack_messages(2)))

        results = list(analyze.load_slack_export(dir_path, "salt"))

        assert len(results) == 5
        channels = {m.channel for m in results}
        assert channels == {"general", "random"}

    def test_zip_export(self, tmp_path):
        zip_path = tmp_path / "export.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("general.json", json.dumps(_make_slack_messages(3)))
            zf.writestr("random.json", json.dumps(_make_slack_messages(2)))

        results = list(analyze.load_slack_export(zip_path, "salt"))

        assert len(results) == 5

    def test_skips_bot_messages(self, tmp_path):
        msgs = [
            {
                "type": "message",
                "user": "U12345",
                "ts": "1704067200.000000",
                "text": "real user",
            },
            {
                "type": "message",
                "user": "B12345",
                "ts": "1704067200.000001",
                "text": "bot msg",
            },
        ]
        path = tmp_path / "test.json"
        path.write_text(json.dumps(msgs))

        results = list(analyze.load_slack_export(path, "salt"))
        assert len(results) == 1
        assert results[0].content == "real user"

    def test_skips_system_subtypes(self, tmp_path):
        msgs = [
            {
                "type": "message",
                "user": "U1",
                "ts": "1704067200.000000",
                "text": "hello",
                "subtype": None,
            },
            {
                "type": "message",
                "user": "U2",
                "ts": "1704067200.000001",
                "text": "",
                "subtype": "channel_join",
            },
            {
                "type": "message",
                "user": "U3",
                "ts": "1704067200.000002",
                "text": "",
                "subtype": "channel_leave",
            },
        ]
        path = tmp_path / "test.json"
        path.write_text(json.dumps(msgs))

        results = list(analyze.load_slack_export(path, "salt"))
        assert len(results) == 1

    def test_thread_reply_detection(self, tmp_path):
        msgs = [
            {
                "type": "message",
                "user": "U1",
                "ts": "1704067200.000000",
                "text": "parent",
            },
            {
                "type": "message",
                "user": "U2",
                "ts": "1704067200.000001",
                "text": "reply",
                "thread_ts": "1704067200.000000",
            },
        ]
        path = tmp_path / "test.json"
        path.write_text(json.dumps(msgs))

        results = list(analyze.load_slack_export(path, "salt"))
        assert len(results) == 2
        assert results[1].reply_to_message_id == "1704067200.000000"
        assert results[0].reply_to_message_id is None

    def test_timestamps_parsed(self, tmp_path):
        msgs = _make_slack_messages(1)
        path = tmp_path / "test.json"
        path.write_text(json.dumps(msgs))

        results = list(analyze.load_slack_export(path, "salt"))
        assert results[0].timestamp.year == 2024


class TestCSVAdapter:
    def _make_csv(self, tmp_path, rows: list[dict], fieldnames: list[str]) -> Path:
        path = tmp_path / "export.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_basic_csv(self, tmp_path):
        rows = [
            {
                "content": "hello world",
                "author": "alice",
                "timestamp": "2026-01-01T12:00:00+00:00",
            },
            {
                "content": "second msg",
                "author": "bob",
                "timestamp": "2026-01-02T12:00:00+00:00",
            },
        ]
        path = self._make_csv(tmp_path, rows, ["content", "author", "timestamp"])
        results = list(analyze.load_csv_export(path, "salt"))

        assert len(results) == 2
        assert results[0].content == "hello world"
        assert results[0].platform == "csv"
        assert results[0].author_name == "alice"

    def test_column_name_aliases(self, tmp_path):
        """Test that column aliases work (text, user, date)."""
        rows = [
            {
                "text": "alias test",
                "user": "charlie",
                "date": "2026-01-01T12:00:00+00:00",
            },
        ]
        path = self._make_csv(tmp_path, rows, ["text", "user", "date"])
        results = list(analyze.load_csv_export(path, "salt"))

        assert len(results) == 1
        assert results[0].content == "alias test"
        assert results[0].author_name == "charlie"

    def test_case_insensitive_headers(self, tmp_path):
        rows = [
            {
                "Content": "case test",
                "Author": "dave",
                "Timestamp": "2026-01-01T12:00:00+00:00",
            },
        ]
        path = self._make_csv(tmp_path, rows, ["Content", "Author", "Timestamp"])
        results = list(analyze.load_csv_export(path, "salt"))

        assert len(results) == 1
        assert results[0].content == "case test"

    def test_skips_empty_content(self, tmp_path):
        rows = [
            {
                "content": "real msg",
                "author": "a",
                "timestamp": "2026-01-01T12:00:00+00:00",
            },
            {"content": "", "author": "b", "timestamp": "2026-01-02T12:00:00+00:00"},
        ]
        path = self._make_csv(tmp_path, rows, ["content", "author", "timestamp"])
        results = list(analyze.load_csv_export(path, "salt"))

        assert len(results) == 1

    def test_channel_column(self, tmp_path):
        rows = [
            {
                "content": "msg1",
                "author": "a",
                "timestamp": "2026-01-01T12:00:00+00:00",
                "channel": "general",
            },
            {
                "content": "msg2",
                "author": "b",
                "timestamp": "2026-01-02T12:00:00+00:00",
                "channel": "random",
            },
        ]
        path = self._make_csv(
            tmp_path, rows, ["content", "author", "timestamp", "channel"]
        )
        results = list(analyze.load_csv_export(path, "salt"))

        assert results[0].channel == "general"
        assert results[1].channel == "random"

    def test_missing_timestamp_defaults_epoch(self, tmp_path):
        rows = [{"content": "no ts", "author": "a"}]
        path = self._make_csv(tmp_path, rows, ["content", "author"])
        results = list(analyze.load_csv_export(path, "salt"))

        assert len(results) == 1
        # Should be datetime.min, not crash

    def test_author_id_hashed(self, tmp_path):
        rows = [
            {
                "content": "msg",
                "author_id": "U12345",
                "timestamp": "2026-01-01T12:00:00+00:00",
            }
        ]
        path = self._make_csv(tmp_path, rows, ["content", "author_id", "timestamp"])
        results = list(analyze.load_csv_export(path, "salt"))

        assert len(results) == 1
        assert results[0].author_id != "U12345"
        assert len(results[0].author_id) == 16  # SHA-256 hexdigest[:16]


class TestCanonicalSchema:
    def test_schema_file_exists(self):
        from parallax.core.config import _config_dir

        schema_path = _config_dir() / "canonical_schema.json"
        assert schema_path.exists()

    def test_schema_is_valid_json(self):
        from parallax.core.config import _config_dir

        schema_path = _config_dir() / "canonical_schema.json"
        data = json.loads(schema_path.read_text())
        assert data["title"] == "Parallax Canonical Chat Export"
        assert "messages" in data["properties"]
        assert "message" in data["$defs"]

    def test_canonical_adapter_loads_valid(self, tmp_path):
        export = {
            "messages": [
                {
                    "platform": "whatsapp",
                    "channel": "family",
                    "message_id": "1",
                    "author_id": "u1",
                    "author_name": "Alice",
                    "timestamp": "2026-01-01T12:00:00+00:00",
                    "content": "hello from whatsapp",
                }
            ]
        }
        path = tmp_path / "export.json"
        path.write_text(json.dumps(export))

        results = list(analyze.load_canonical(path, "salt"))
        assert len(results) == 1
        assert results[0].platform == "whatsapp"
        assert results[0].content == "hello from whatsapp"
        assert results[0].author_name == "Alice"
