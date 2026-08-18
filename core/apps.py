import importlib
from pathlib import Path

from .config import APPS

REGISTRY = []


def load_apps(app):

    loaded = []

    for directory in sorted(APPS.iterdir()):

        if not directory.is_dir():
            continue

        if not (directory / "__init__.py").exists():
            continue

        module = importlib.import_module(f"apps.{directory.name}")

        app.register_blueprint(module.bp)

        if getattr(module, "HIDDEN", False):
            continue

        loaded.append({
            "id": directory.name,
            "name": getattr(module, "NAME", directory.name.capitalize()),
            "description": getattr(module, "DESCRIPTION", ""),
            "help_intro": getattr(module, "HELP_INTRO", ""),
            "commands": getattr(module, "COMMANDS", []),
            "multiview": getattr(module, "MULTIVIEW", False),
        })

    REGISTRY[:] = loaded

    return loaded


def resolve_launch(query, apps):

    token = query.strip()

    if not token or " " in token or "\n" in token:
        return None

    token = token.lower()

    exact = [
        a for a in apps
        if a["id"].lower() == token or a["name"].lower() == token
    ]

    if exact:
        return exact[0]["id"]

    prefix = [
        a for a in apps
        if a["id"].lower().startswith(token) or a["name"].lower().startswith(token)
    ]

    if len(prefix) == 1:
        return prefix[0]["id"]

    return None
