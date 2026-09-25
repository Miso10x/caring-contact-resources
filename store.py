"""SQLite storage for the resource finder.

Every record is a JSON document in one table, keyed by (collection, id). The
page edits whole documents, so there is nothing to gain from a column per field,
and staff can add fields later without a migration.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

COLLECTIONS = ("resources", "categories", "notices", "settings", "available")
ADMIN_ONLY = ("available",)
HERE = os.path.dirname(os.path.abspath(__file__))
SEED_FILE = os.path.join(HERE, "seed_data.json")


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
    conn.execute("CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
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


def _get(conn, collection, doc_id):
    row = conn.execute("SELECT data FROM docs WHERE collection = ? AND id = ?", (collection, doc_id)).fetchone()
    return json.loads(row[0]) if row else None


def _add_websites(conn):
    """Fill in agency websites that were checked on 2026-09-25, only where a listing has none."""
    with open(os.path.join(HERE, "website_additions.json"), encoding="utf-8") as f:
        sites = json.load(f)
    for doc_id, url in sites.items():
        doc = _get(conn, "resources", doc_id)
        if doc is not None and not doc.get("website"):
            doc["website"] = url
            _put(conn, "resources", doc_id, doc)
    doc = _get(conn, "resources", "mh-support-nj-mentalhealthcares")
    if doc is not None and not any("877-294-4356" in p.get("number", "") for p in doc.get("phones", [])):
        doc.setdefault("phones", []).append({"label": "TTY (Deaf / hard of hearing)", "number": "1-877-294-4356"})
        _put(conn, "resources", "mh-support-nj-mentalhealthcares", doc)


def _add_available(conn):
    """Offer resources from the NJ Division of Disability Services mental health page for staff to add."""
    with open(os.path.join(HERE, "additional_resources.json"), encoding="utf-8") as f:
        items = json.load(f)
    source = items.pop("_source")
    for doc_id, data in items.items():
        if _get(conn, "available", doc_id) is None and _get(conn, "resources", doc_id) is None:
            _put(conn, "available", doc_id, {**data, "source": source})


# Each runs once per database, in order, after seeding. Append new ones; never edit an applied one.
MIGRATIONS = [("2026-09-25-websites", _add_websites), ("2026-09-25-available", _add_available)]


def migrate():
    with connect() as conn:
        done = {r[0] for r in conn.execute("SELECT name FROM migrations")}
        for name, fn in MIGRATIONS:
            if name in done:
                continue
            fn(conn)
            conn.execute("INSERT OR IGNORE INTO migrations (name, applied_at) VALUES (?, ?)", (name, datetime.now(timezone.utc).isoformat()))


def all_docs(include_admin=True):
    out = {c: [] for c in COLLECTIONS if include_admin or c not in ADMIN_ONLY}
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
