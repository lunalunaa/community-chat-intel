"""SQLite state store for incremental analysis.

Tracks which messages have been processed, so re-running parallax-analyze
on an updated export only processes new messages and merges the results
into the existing stats.

Usage:
    store = StateStore(Path("./out/parallax_state.db"))
    store.mark_seen(messages)           # record message IDs as processed
    new_msgs = store.filter_new(all_msgs)  # get only unprocessed messages

The store is per-export-file: the file path is hashed to create a
namespace, so analyzing different exports doesn't cross-contaminate.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parallax.core.analyze import Message


def _export_key(file_path: str) -> str:
    """Hash the export file path to create a namespace key."""
    return hashlib.sha256(file_path.encode()).hexdigest()[:16]


class StateStore:
    """SQLite-backed state store for incremental analysis."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_messages (
                export_key TEXT NOT NULL,
                message_id TEXT NOT NULL,
                seen_at TEXT NOT NULL,
                PRIMARY KEY (export_key, message_id)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS export_state (
                export_key TEXT PRIMARY KEY,
                export_path TEXT NOT NULL,
                last_run_at TEXT NOT NULL,
                total_processed INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._conn.commit()

    def filter_new(self, messages: list[Message], export_path: str) -> list[Message]:
        """Return only messages not yet seen for this export."""
        key = _export_key(str(export_path))
        # Batch query for efficiency
        seen: set[str] = set()
        cursor = self._conn.execute(
            "SELECT message_id FROM seen_messages WHERE export_key = ?",
            (key,),
        )
        for row in cursor:
            seen.add(row[0])
        return [m for m in messages if m.message_id not in seen]

    def mark_seen(self, messages: list[Message], export_path: str) -> int:
        """Mark messages as seen. Returns count of newly-marked messages."""
        from datetime import datetime, timezone

        key = _export_key(str(export_path))
        now = datetime.now(tz=timezone.utc).isoformat()
        count = 0
        for m in messages:
            if not m.message_id:
                continue
            try:
                self._conn.execute(
                    "INSERT OR IGNORE INTO seen_messages (export_key, message_id, seen_at) VALUES (?, ?, ?)",
                    (key, m.message_id, now),
                )
                if self._conn.total_changes > 0:
                    count += 1
            except sqlite3.IntegrityError:
                pass
        # Update export state
        self._conn.execute(
            """INSERT INTO export_state (export_key, export_path, last_run_at, total_processed)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(export_key) DO UPDATE SET
                   last_run_at = excluded.last_run_at,
                   total_processed = export_state.total_processed + excluded.total_processed
            """,
            (key, str(export_path), now, len(messages)),
        )
        self._conn.commit()
        return count

    def get_state(self, export_path: str) -> dict | None:
        """Get the last-known state for an export path."""
        key = _export_key(str(export_path))
        cursor = self._conn.execute(
            "SELECT export_path, last_run_at, total_processed FROM export_state WHERE export_key = ?",
            (key,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "export_path": row[0],
            "last_run_at": row[1],
            "total_processed": row[2],
        }

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
