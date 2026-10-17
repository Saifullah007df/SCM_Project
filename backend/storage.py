"""Small SQLite repository with serialized transactions and hash-chained audit events.

The demo uses standard-library SQLite rather than an ORM. A versioned schema
and a single process keep installation and crash recovery straightforward.
"""
import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_versions VALUES (1);
        CREATE TABLE IF NOT EXISTS records(
          kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
          PRIMARY KEY(kind,id));
        CREATE TABLE IF NOT EXISTS audit(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL,
          event TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
        ''')

    @contextmanager
    def transaction(self):
        with self.lock:
            nested = self.db.in_transaction
            if not nested:
                self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                if not nested:
                    self.db.execute('COMMIT')
            except BaseException:
                if not nested and self.db.in_transaction:
                    self.db.execute('ROLLBACK')
                raise

    def get(self, kind, ident):
        with self.lock:
            row = self.db.execute('SELECT data FROM records WHERE kind=? AND id=?', (kind, ident)).fetchone()
            return json.loads(row[0]) if row else None

    def all(self, kind):
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute('SELECT data FROM records WHERE kind=? ORDER BY rowid', (kind,))]

    def put(self, kind, value):
        with self.lock:
            self.db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data',
                            (kind, value['id'], canonical(value)))
        return value

    def delete(self, kind, ident):
        with self.lock:
            self.db.execute('DELETE FROM records WHERE kind=? AND id=?', (kind, ident))

    def audit(self, action, actor='system', **details):
        with self.transaction():
            row = self.db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
            previous = row[0] if row else '0' * 64
            timestamp = now()
            event = canonical({'action': action, 'actor': actor, **details})
            digest = hashlib.sha256((previous + timestamp + event).encode()).hexdigest()
            self.db.execute('INSERT INTO audit(time,event,previous_hash,hash) VALUES(?,?,?,?)',
                            (timestamp, event, previous, digest))

    def events(self):
        with self.lock:
            return [{'seq': r[0], 'time': r[1], **json.loads(r[2]), 'previous_hash': r[3], 'hash': r[4]}
                    for r in self.db.execute('SELECT seq,time,event,previous_hash,hash FROM audit ORDER BY seq DESC')]

    def verify_audit(self):
        previous = '0' * 64
        with self.lock:
            for timestamp, event, prev, digest in self.db.execute('SELECT time,event,previous_hash,hash FROM audit ORDER BY seq'):
                if prev != previous or hashlib.sha256((prev + timestamp + event).encode()).hexdigest() != digest:
                    return False
                previous = digest
        return True
