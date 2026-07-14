import time

from . import db

LOCK_TTL = 300  # seconds of inactivity before an abandoned lock (closed tab,
                 # crash, dead connection) can be taken over by someone else -
                 # generous enough that a normal pause to read/think doesn't
                 # cost you the lock


def acquire(workspace_id, path, user_id):
    """Try to lock (workspace_id, path) for user_id - editing gated behind
    this so two people can't silently clobber each other's changes to the
    same file. Returns (True, None) on success, or (False, holder_username)
    if someone else holds a still-live lock. Re-acquiring your own lock (or
    a save while you already hold it) just refreshes the timestamp - this
    doubles as the autosave heartbeat that keeps a genuinely active edit
    session from going stale mid-way through."""

    with db.connect() as con:
        row = con.execute(
            "SELECT file_locks.user_id, users.username, file_locks.acquired_at "
            "FROM file_locks JOIN users ON users.id = file_locks.user_id "
            "WHERE workspace_id = ? AND path = ?",
            (workspace_id, path),
        ).fetchone()

        if row and row["user_id"] != user_id and time.time() - row["acquired_at"] < LOCK_TTL:
            return False, row["username"]

        con.execute(
            "INSERT INTO file_locks (workspace_id, path, user_id, acquired_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(workspace_id, path) DO UPDATE SET "
            "user_id = excluded.user_id, acquired_at = excluded.acquired_at",
            (workspace_id, path, user_id, time.time()),
        )

        return True, None


def release(workspace_id, path, user_id):
    with db.connect() as con:
        con.execute(
            "DELETE FROM file_locks WHERE workspace_id = ? AND path = ? AND user_id = ?",
            (workspace_id, path, user_id),
        )


def holder(workspace_id, path):
    """Who currently holds a live (non-stale) lock on this file, if
    anyone - used to render the file read-only for everyone but them."""

    with db.connect() as con:
        row = con.execute(
            "SELECT file_locks.user_id, users.username, file_locks.acquired_at "
            "FROM file_locks JOIN users ON users.id = file_locks.user_id "
            "WHERE workspace_id = ? AND path = ?",
            (workspace_id, path),
        ).fetchone()

        if row and time.time() - row["acquired_at"] < LOCK_TTL:
            return row["user_id"], row["username"]

        return None, None
