from pathlib import Path
import subprocess

from .config import WORKSPACES, ARK
from .db import connect


def path(username):

    return WORKSPACES / username


def create(user):

    root = path(user)

    ark = root / "ark"

    apps = root / "apps"

    ark.mkdir(parents=True, exist_ok=True)

    apps.mkdir(parents=True, exist_ok=True)

    if not (ark / ".ark").exists():

        subprocess.run(
            [str(ARK), "init"],
            cwd=ark,
            check=False,
        )
