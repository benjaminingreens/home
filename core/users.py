import hashlib
import os
import sqlite3

from .db import connect
from .workspaces import create as create_workspace

PBKDF2_ITERATIONS = 260_000


def hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    ).hex()

    return f"{salt}${digest}"


def verify_password(password, stored):
    if "$" not in stored:
        # legacy unsalted sha256 hash
        return hashlib.sha256(password.encode()).hexdigest() == stored

    salt, _ = stored.split("$", 1)
    return hash_password(password, salt) == stored


def create(username, password, is_admin=False, must_change_password=False):

    username = username.strip().lower()

    with connect() as con:

        con.execute(
            """
            INSERT INTO users(username, password, is_admin, must_change_password)
            VALUES (?, ?, ?, ?)
            """,
            (username, hash_password(password), int(is_admin), int(must_change_password)),
        )

    create_workspace(username)


def authenticate(username, password):

    with connect() as con:

        row = con.execute(
            """
            SELECT *
            FROM users
            WHERE username=?
            """,
            (username.strip().lower(),),
        ).fetchone()

    if row is None:
        return None

    if not verify_password(password, row["password"]):
        return None

    if "$" not in row["password"]:
        with connect() as con:
            con.execute(
                "UPDATE users SET password=? WHERE id=?",
                (hash_password(password), row["id"]),
            )

    return row


def update_password(user_id, new_password, must_change_password=False):

    with connect() as con:

        con.execute(
            "UPDATE users SET password=?, must_change_password=? WHERE id=?",
            (hash_password(new_password), int(must_change_password), user_id),
        )


def list_users():

    with connect() as con:

        return con.execute(
            "SELECT id, username, is_admin, must_change_password FROM users ORDER BY username"
        ).fetchall()


def has_any_users():

    with connect() as con:
        return con.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def create_first_admin(username, password):
    """Used only by the one-time /setup screen, which is itself gated on
    has_any_users() being False. The IntegrityError guard covers the race
    between that check and this insert (e.g. two gunicorn workers handling
    near-simultaneous first-run requests)."""

    try:
        create(username, password, is_admin=True)
        return True
    except sqlite3.IntegrityError:
        return False
