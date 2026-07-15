import time

from . import db

# A page-view sync check only actually runs this often per workspace -
# any request that lands inside the window just serves what's already on
# disk. This decouples git-operation frequency from concurrent request
# volume: 1 viewer or 1000 viewers in the same window cost the same one
# fetch, instead of one fetch per request.
SYNC_THROTTLE_SECONDS = 5


def get(workspace_id):
    with db.connect() as con:
        row = con.execute(
            "SELECT status, conflict_files, remote_sha, version, last_synced_at "
            "FROM workspace_sync_state WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()

    if not row:
        return {"status": "clean", "conflict_files": [], "remote_sha": "", "version": 0, "last_synced_at": 0}

    return {
        "status": row["status"],
        "conflict_files": [f for f in row["conflict_files"].split(",") if f],
        "remote_sha": row["remote_sha"],
        "version": row["version"],
        "last_synced_at": row["last_synced_at"],
    }


def is_conflicted(workspace_id):
    return get(workspace_id)["status"] == "conflict"


def due_for_sync(workspace_id):
    return time.time() - get(workspace_id)["last_synced_at"] >= SYNC_THROTTLE_SECONDS


def mark_synced(workspace_id):
    """Stamps "just checked the remote" - called whether or not the check
    found anything, so a run of offline requests also backs off to once
    per window instead of retrying the network every time."""

    with db.connect() as con:
        con.execute(
            "INSERT INTO workspace_sync_state (workspace_id, last_synced_at) VALUES (?, ?) "
            "ON CONFLICT(workspace_id) DO UPDATE SET last_synced_at = excluded.last_synced_at",
            (workspace_id, time.time()),
        )


def mark_conflict(workspace_id, conflict_files, remote_sha):
    with db.connect() as con:
        con.execute(
            "INSERT INTO workspace_sync_state (workspace_id, status, conflict_files, remote_sha, version) "
            "VALUES (?, 'conflict', ?, ?, 1) "
            "ON CONFLICT(workspace_id) DO UPDATE SET "
            "status = 'conflict', conflict_files = excluded.conflict_files, "
            "remote_sha = excluded.remote_sha, version = workspace_sync_state.version + 1",
            (workspace_id, ",".join(conflict_files), remote_sha),
        )


def mark_clean(workspace_id, expected_version):
    """Clears a conflict, but only if it's still the same one the caller
    resolved - if someone else in the group already resolved it (or a new
    conflict has replaced it), this is a no-op and returns False, so the
    resolver gets "already resolved" instead of silently clobbering
    whatever's there now."""

    with db.connect() as con:
        cur = con.execute(
            "UPDATE workspace_sync_state SET status = 'clean', conflict_files = '', remote_sha = '' "
            "WHERE workspace_id = ? AND version = ? AND status = 'conflict'",
            (workspace_id, expected_version),
        )

        return cur.rowcount > 0
