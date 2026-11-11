import json
from datetime import datetime, timezone


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    project TEXT NOT NULL,
    kind TEXT NOT NULL,
    origin TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    project TEXT NOT NULL,
    kind TEXT NOT NULL,
    event_key TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    payload TEXT NOT NULL,
    UNIQUE (project, kind, event_key)
);
"""


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Timestamp requires a timezone offset, e.g. +00:00.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def save(connection, project, kind, origin, fingerprint, records):
    with connection:
        # Acquire the write lock before checking for duplicates.
        connection.execute("BEGIN IMMEDIATE")
        fresh = []
        for key, timestamp, payload in records:
            exists = connection.execute(
                "SELECT 1 FROM events WHERE project=? AND kind=? AND event_key=?",
                (project, kind, key),
            ).fetchone()
            if not exists:
                fresh.append((key, timestamp, payload))
        if not fresh:
            return 0
        source_id = connection.execute(
            "INSERT INTO sources(project, kind, origin, fingerprint, imported_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (project, kind, origin, fingerprint, datetime.now(timezone.utc).isoformat()),
        ).lastrowid
        connection.executemany(
            "INSERT INTO events(project, kind, event_key, occurred_at, source_id, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(project, kind, key, timestamp, source_id, json.dumps(payload))
             for key, timestamp, payload in fresh],
        )
        return len(fresh)


def events(connection, project):
    rows = connection.execute(
        "SELECT e.id, e.kind, e.occurred_at, e.payload, s.origin, s.fingerprint "
        "FROM events e JOIN sources s ON s.id=e.source_id "
        "WHERE e.project=? ORDER BY e.occurred_at, e.id",
        (project,),
    )
    return [
        dict(id=event_id, kind=kind, time=time, data=json.loads(payload),
             origin=origin, fingerprint=fingerprint)
        for event_id, kind, time, payload, origin, fingerprint in rows
    ]
