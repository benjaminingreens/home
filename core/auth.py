from flask import session

from .users import authenticate
from .db import connect


def login(username, password):

    user = authenticate(username, password)

    if not user:
        return False

    session["user"] = user["id"]

    return True


def logout():
    session.clear()


def current_user():

    uid = session.get("user")

    if uid is None:
        return None

    with connect() as con:

        return con.execute(
            "SELECT * FROM users WHERE id=?",
            (uid,),
        ).fetchone()
