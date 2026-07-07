from flask import session

from .users import authenticate


def login(username, password):

    user = authenticate(username, password)

    if not user:
        return False

    session["user"] = user["id"]

    return True


def logout():

    session.clear()


def current_user():

    return session.get("user")
