from pathlib import Path

from .config import WORKSPACES


def path(user):

    return WORKSPACES / user


def app(user, app):

    return path(user) / app


def create(user):

    root = path(user)

    root.mkdir(parents=True, exist_ok=True)
