from hashlib import sha256

from .db import connect


def hash_password(password):
    return sha256(password.encode()).hexdigest()


def create(username, password):

    with connect() as con:

        con.execute(
            """
            INSERT INTO users(username,password)
            VALUES(?,?)
            """,
            (username, hash_password(password)),
        )


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

    if row["password"] != hash_password(password):
        return None

    return row
