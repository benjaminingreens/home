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


def ensure_admin():

    username = os.environ.get("HOME_ADMIN_USER")
    password = os.environ.get("HOME_ADMIN_PASSWORD")

    if not username or not password:
        return

    username = username.strip().lower()

    with connect() as con:
        existing = con.execute(
            "SELECT id FROM users WHERE username=?", (username,)
        ).fetchone()

    if existing:
        return

    try:
        create(username, password, is_admin=True, must_change_password=True)
    except sqlite3.IntegrityError:
        # another gunicorn worker won the race to create this account
        pass
