"""SQLite storage for the resource finder.

Every record is a JSON document in one table, keyed by (collection, id). The
page edits whole documents, so there is nothing to gain from a column per field,
and staff can add fields later without a migration.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

COLLECTIONS = ("resources", "categories", "notices", "settings")
SEED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data.json")


def db_path():
    return os.path.join(os.environ.get("DATA_DIR", "./data"), "resources.db")


def connect():
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS docs (collection TEXT NOT NULL, id TEXT NOT NULL,"
        " data TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (collection, id))"
    )
    return conn


def seed_if_empty(seed_file=SEED_FILE):
    """Load the starting resources, but only into an empty database.

    Never re-seeds a database that has data: a re-seed on every deploy would
    silently undo every edit staff made.
    """
    with connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]:
            return 0
        with open(seed_file, encoding="utf-8") as f:
            seed = json.load(f)
        n = 0
        for collection, docs in seed.items():
            for doc_id, data in docs.items():
                _put(conn, collection, doc_id, data)
                n += 1
        return n


def all_docs():
    out = {c: [] for c in COLLECTIONS}
    with connect() as conn:
        for collection, doc_id, data in conn.execute("SELECT collection, id, data FROM docs ORDER BY collection, id"):
            if collection in out:
                out[collection].append({"id": doc_id, "data": json.loads(data)})
    return out


def _put(conn, collection, doc_id, data):
    conn.execute(
        "INSERT INTO docs (collection, id, data, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (collection, id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
        (collection, doc_id, json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
    )


def put(collection, doc_id, data):
    with connect() as conn:
        _put(conn, collection, doc_id, data)


def delete(collection, doc_id):
    with connect() as conn:
        conn.execute("DELETE FROM docs WHERE collection = ? AND id = ?", (collection, doc_id))
