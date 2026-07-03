"""Tests for incremental analysis: state store, stats merging, and diff."""

import json
from datetime import datetime, timezone


from parallax.core import analyze
from parallax.core.diff import diff_stats, diff_stats_json
from parallax.core.state import StateStore


def _make_message(
    msg_id: str, content: str = "hello", author: str = "u1"
) -> analyze.Message:
    return analyze.Message(
        platform="discord",
        channel="general",
        message_id=msg_id,
        author_id=author,
        author_name="test",
        timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc),
        content=content,
    )


class TestStateStore:
    def test_filter_new_returns_all_on_first_run(self, tmp_path):
        store = StateStore(tmp_path / "state.db")
        msgs = [_make_message("1"), _make_message("2"), _make_message("3")]
        new = store.filter_new(msgs, "/tmp/export.json")
        assert len(new) == 3
        store.close()

    def test_mark_seen_then_filter_new(self, tmp_path):
        store = StateStore(tmp_path / "state.db")
        msgs = [_make_message("1"), _make_message("2"), _make_message("3")]
        store.mark_seen(msgs, "/tmp/export.json")

        # All 3 should now be filtered out
        new = store.filter_new(msgs, "/tmp/export.json")
        assert len(new) == 0
        store.close()

    def test_partial_new(self, tmp_path):
        store = StateStore(tmp_path / "state.db")
        old_msgs = [_make_message("1"), _make_message("2")]
        store.mark_seen(old_msgs, "/tmp/export.json")

        all_msgs = [
            _make_message("1"),
            _make_message("2"),
            _make_message("3"),
            _make_message("4"),
        ]
        new = store.filter_new(all_msgs, "/tmp/export.json")
        assert len(new) == 2
        assert new[0].message_id == "3"
        assert new[1].message_id == "4"
        store.close()

    def test_different_exports_dont_cross_contaminate(self, tmp_path):
        store = StateStore(tmp_path / "state.db")
        msgs_a = [_make_message("1"), _make_message("2")]
        store.mark_seen(msgs_a, "/tmp/export_a.json")

        # Same message IDs but different export path should still be "new"
        new = store.filter_new(msgs_a, "/tmp/export_b.json")
        assert len(new) == 2
        store.close()

    def test_get_state_returns_none_for_unknown(self, tmp_path):
        store = StateStore(tmp_path / "state.db")
        assert store.get_state("/tmp/unknown.json") is None
        store.close()

    def test_get_state_returns_data_after_mark(self, tmp_path):
        store = StateStore(tmp_path / "state.db")
        msgs = [_make_message("1"), _make_message("2")]
        store.mark_seen(msgs, "/tmp/export.json")
        state = store.get_state("/tmp/export.json")
        assert state is not None
        assert state["total_processed"] == 2
        store.close()

    def test_context_manager(self, tmp_path):
        with StateStore(tmp_path / "state.db") as store:
            msgs = [_make_message("1")]
            store.mark_seen(msgs, "/tmp/export.json")
            new = store.filter_new(msgs, "/tmp/export.json")
            assert len(new) == 0


class TestMergeStats:
    def _make_stats(self, msgs=10, providers=None, friction=None) -> dict:
        return {
            "metadata": {
                "total_messages": msgs,
                "channels": ["general"],
                "channel_message_counts": {"general": msgs},
                "channel_target_message_counts": {"general": msgs},
                "channel_zh_message_counts": {"general": msgs},
                "date_range": [
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-15T00:00:00+00:00",
                ],
                "pipeline_version": "0.4.0",
            },
            "language_distribution": {"target": msgs},
            "users": {"total": 5, "target_primary": 3, "target_plus_bilingual": 3},
            "providers": providers or {"openai": 5},
            "friction_signals": friction or {"error_generic": 3},
            "help_answered": {
                "total_questions": 4,
                "target_answered": 2,
                "target_answered_rate": 0.5,
            },
            "location_proxy": {"mainland_evening": 3},
            "competitors": {},
            "messaging_platforms": {},
            "features": {},
            "install_paths": {},
            "shadow_community_mentions": {},
        }

    def test_merge_sums_counters(self):
        old = self._make_stats(msgs=10, providers={"openai": 5})
        new = self._make_stats(msgs=5, providers={"openai": 3, "anthropic_claude": 2})
        merged = analyze.merge_stats(old, new)

        assert merged["providers"]["openai"] == 8  # 5 + 3
        assert merged["providers"]["anthropic_claude"] == 2

    def test_merge_sums_total_messages(self):
        old = self._make_stats(msgs=100)
        new = self._make_stats(msgs=50)
        merged = analyze.merge_stats(old, new)

        assert merged["metadata"]["total_messages"] == 150

    def test_merge_marks_incremental(self):
        old = self._make_stats(msgs=10)
        new = self._make_stats(msgs=5)
        merged = analyze.merge_stats(old, new)

        assert merged["metadata"]["incremental_merge"] is True
        assert merged["metadata"]["previous_total_messages"] == 10

    def test_merge_widens_date_range(self):
        old = self._make_stats(msgs=10)
        old["metadata"]["date_range"] = [
            "2026-01-01T00:00:00+00:00",
            "2026-01-10T00:00:00+00:00",
        ]
        new = self._make_stats(msgs=5)
        new["metadata"]["date_range"] = [
            "2026-01-05T00:00:00+00:00",
            "2026-01-20T00:00:00+00:00",
        ]
        merged = analyze.merge_stats(old, new)

        assert merged["metadata"]["date_range"][0] == "2026-01-01T00:00:00+00:00"
        assert merged["metadata"]["date_range"][1] == "2026-01-20T00:00:00+00:00"

    def test_merge_sums_help_answered(self):
        old = self._make_stats(msgs=10)
        old["help_answered"] = {
            "total_questions": 10,
            "target_answered": 5,
            "target_answered_rate": 0.5,
        }
        new = self._make_stats(msgs=5)
        new["help_answered"] = {
            "total_questions": 5,
            "target_answered": 4,
            "target_answered_rate": 0.8,
        }
        merged = analyze.merge_stats(old, new)

        assert merged["help_answered"]["total_questions"] == 15
        assert merged["help_answered"]["target_answered"] == 9
        assert merged["help_answered"]["target_answered_rate"] == 9 / 15

    def test_merge_takes_max_users(self):
        old = self._make_stats(msgs=10)
        old["users"]["total"] = 20
        new = self._make_stats(msgs=5)
        new["users"]["total"] = 15
        merged = analyze.merge_stats(old, new)

        # max(20, 15) = 20 (conservative: can't know overlap without full data)
        assert merged["users"]["total"] == 20


class TestDiff:
    def _make_stats(self, msgs=10, providers=None) -> dict:
        return {
            "metadata": {
                "total_messages": msgs,
                "date_range": [
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-15T00:00:00+00:00",
                ],
            },
            "users": {"total": 5},
            "help_answered": {"total_questions": 4, "target_answered_rate": 0.5},
            "friction_signals": {"error_generic": 3},
            "providers": providers or {"openai": 5},
            "competitors": {},
            "messaging_platforms": {},
            "features": {},
            "install_paths": {},
            "shadow_community_mentions": {},
            "language_distribution": {},
            "location_proxy": {},
        }

    def test_diff_text_output(self):
        old = self._make_stats(msgs=100, providers={"openai": 5})
        new = self._make_stats(msgs=150, providers={"openai": 8, "anthropic_claude": 3})
        result = diff_stats(old, new)

        assert "Messages" in result
        assert "100" in result
        assert "150" in result
        assert "openai" in result
        assert "anthropic_claude" in result
        assert "[new]" in result

    def test_diff_json_output(self):
        old = self._make_stats(msgs=100, providers={"openai": 5})
        new = self._make_stats(msgs=150, providers={"openai": 8, "anthropic_claude": 3})
        result = diff_stats_json(old, new)

        assert result["kpi"]["messages"]["old"] == 100
        assert result["kpi"]["messages"]["new"] == 150
        assert "openai" in result["counters"]["providers"]
        assert result["counters"]["providers"]["openai"]["old"] == 5
        assert result["counters"]["providers"]["openai"]["new"] == 8

    def test_diff_no_changes(self):
        old = self._make_stats(msgs=10, providers={"openai": 5})
        new = self._make_stats(msgs=10, providers={"openai": 5})
        result = diff_stats_json(old, new)

        # No counter changes
        assert "providers" not in result["counters"]

    def test_diff_detects_disappeared_items(self):
        old = self._make_stats(msgs=10, providers={"openai": 5, "old_provider": 3})
        new = self._make_stats(msgs=10, providers={"openai": 5})
        result = diff_stats(old, new)

        assert "old_provider" in result
        assert "[gone]" in result

    def test_diff_cli_runs(self, tmp_path):
        old = self._make_stats(msgs=100)
        new = self._make_stats(msgs=150)
        old_path = tmp_path / "old.json"
        new_path = tmp_path / "new.json"
        old_path.write_text(json.dumps(old))
        new_path.write_text(json.dumps(new))

        from parallax.core.diff import main
        import sys

        old_argv = sys.argv
        sys.argv = ["parallax-diff", "--old", str(old_path), "--new", str(new_path)]
        try:
            rc = main()
            assert rc == 0
        finally:
            sys.argv = old_argv
