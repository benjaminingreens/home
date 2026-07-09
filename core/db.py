import sqlite3

from .config import DATABASE

def connect():
    con = sqlite3.connect(DATABASE)
    con.row_factory = sqlite3.Row
    return con


def init():

    with connect() as con:

        con.executescript("""

        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY,

            username TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL

        );

        CREATE TABLE IF NOT EXISTS workspaces (

            id INTEGER PRIMARY KEY,

            owner INTEGER NOT NULL,

            name TEXT NOT NULL,

            UNIQUE(owner,name)

        );

        """)

        columns = {row["name"] for row in con.execute("PRAGMA table_info(users)")}

        if "is_admin" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

        if "must_change_password" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
