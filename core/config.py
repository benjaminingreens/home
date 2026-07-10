import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA = Path(os.environ.get("HOME_DATA_DIR", "/var/lib/home"))

DATABASE = DATA / "home.db"

WORKSPACES = DATA / "workspaces"

APPS = ROOT / "apps"

SECRET_KEY = os.environ.get("HOME_SECRET_KEY")

GIT_ROOT = DATA / "git"

GIT_HOST = os.environ.get("HOME_GIT_HOST", "")

GIT_SSH_USER = os.environ.get("HOME_GIT_SSH_USER", "")
