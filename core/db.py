import sqlite3

from .config import DATABASE

def connect():
    con = sqlite3.connect(DATABASE)
    con.row_factory = sqlite3.Row
    return con


def init():

    with connect() as con:

        # The pre-groups "workspaces" table (id, owner, name) was dead code
        # (never inserted into or selected from) but may still exist on
        # disk from before this migration. Drop it so the real one below
        # can take its place with the new shape.
        old_workspace_columns = {
            row["name"] for row in con.execute("PRAGMA table_info(workspaces)")
        }

        if "owner" in old_workspace_columns:
            con.execute("DROP TABLE workspaces")

        con.executescript("""

        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY,

            username TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL

        );

        CREATE TABLE IF NOT EXISTS groups (

            id INTEGER PRIMARY KEY,

            slug TEXT UNIQUE NOT NULL,

            name TEXT NOT NULL,

            is_personal INTEGER NOT NULL DEFAULT 0,

            created_by INTEGER NOT NULL

        );

        CREATE TABLE IF NOT EXISTS group_members (

            group_id INTEGER NOT NULL,

            user_id INTEGER NOT NULL,

            status TEXT NOT NULL DEFAULT 'active',

            PRIMARY KEY (group_id, user_id)

        );

        CREATE TABLE IF NOT EXISTS workspaces (

            id INTEGER PRIMARY KEY,

            group_id INTEGER NOT NULL,

            app TEXT NOT NULL,

            name TEXT NOT NULL,

            created_by INTEGER NOT NULL,

            UNIQUE(group_id, app, name)

        );

        CREATE TABLE IF NOT EXISTS workspace_visibility (

            user_id INTEGER NOT NULL,

            workspace_id INTEGER NOT NULL,

            visible INTEGER NOT NULL DEFAULT 1,

            PRIMARY KEY (user_id, workspace_id)

        );

        CREATE TABLE IF NOT EXISTS federated_servers (

            id INTEGER PRIMARY KEY,

            host TEXT UNIQUE NOT NULL,

            status TEXT NOT NULL DEFAULT 'pending'

        );

        CREATE TABLE IF NOT EXISTS file_locks (

            workspace_id INTEGER NOT NULL,

            path TEXT NOT NULL,

            user_id INTEGER NOT NULL,

            acquired_at REAL NOT NULL,

            PRIMARY KEY (workspace_id, path)

        );

        CREATE TABLE IF NOT EXISTS workspace_sync_state (

            workspace_id INTEGER PRIMARY KEY,

            status TEXT NOT NULL DEFAULT 'clean',

            conflict_files TEXT NOT NULL DEFAULT '',

            remote_sha TEXT NOT NULL DEFAULT '',

            version INTEGER NOT NULL DEFAULT 0

        );

        """)

        columns = {row["name"] for row in con.execute("PRAGMA table_info(users)")}

        if "is_admin" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

        if "must_change_password" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")

        if "visibility" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN visibility TEXT NOT NULL DEFAULT 'server'")

        if "active_workspace_id" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN active_workspace_id INTEGER")

        if "accent_color" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN accent_color TEXT NOT NULL DEFAULT '#7fa8e2'")

        if "background_color" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN background_color TEXT NOT NULL DEFAULT '#000000'")
