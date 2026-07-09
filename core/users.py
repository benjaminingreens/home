import hashlib
import os

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


def create(username, password):

    with connect() as con:

        con.execute(
            """
            INSERT INTO users(username,password)
            VALUES(?,?)
            """,
            (username, hash_password(password)),
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
            (username,),
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
