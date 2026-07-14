from . import db


def get(workspace_id):
    with db.connect() as con:
        row = con.execute(
            "SELECT status, conflict_files, remote_sha, version "
            "FROM workspace_sync_state WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()

    if not row:
        return {"status": "clean", "conflict_files": [], "remote_sha": "", "version": 0}

    return {
        "status": row["status"],
        "conflict_files": [f for f in row["conflict_files"].split(",") if f],
        "remote_sha": row["remote_sha"],
        "version": row["version"],
    }


def is_conflicted(workspace_id):
    return get(workspace_id)["status"] == "conflict"


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
