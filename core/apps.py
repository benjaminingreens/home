import importlib
from pathlib import Path

from .config import APPS


def load_apps(app):

    loaded = []

    for directory in sorted(APPS.iterdir()):

        if not directory.is_dir():
            continue

        if not (directory / "__init__.py").exists():
            continue

        module = importlib.import_module(f"apps.{directory.name}")

        app.register_blueprint(module.bp)

        loaded.append({
            "id": directory.name,
            "name": getattr(module, "NAME", directory.name.capitalize()),
            "description": getattr(module, "DESCRIPTION", ""),
        })

    return loaded
