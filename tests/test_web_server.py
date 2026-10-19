import tempfile
import unittest
from pathlib import Path

from hcmus_hub.web_server import initialize_database
from hcmus_hub.store import Store


class DatabaseInitializationTests(unittest.TestCase):
    def test_initializes_schema_and_default_sources_without_replacing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "nested" / "hcmus_hub.sqlite3"
            store = Store(database)
            store.conn.execute(
                """INSERT INTO articles(
                    fingerprint, normalized_title, title, first_seen_at, last_seen_at,
                    read_at, is_favorite
                ) VALUES(?,?,?,?,?,?,?)""",
                ("fingerprint", "title", "Title", "now", "now", "read", 1),
            )
            store.conn.commit()
            store.close()

            initialize_database(database)

            migrated = Store(database)
            try:
                article = migrated.conn.execute(
                    "SELECT read_at, is_favorite FROM articles"
                ).fetchone()
                source_count = migrated.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
                self.assertEqual(tuple(article), ("read", 1))
                self.assertGreater(source_count, 0)
            finally:
                migrated.close()
