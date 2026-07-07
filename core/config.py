from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent

DATA = Path(
    os.environ.get(
        "HOME_DATA",
        ROOT / "data",
    )
)

WORKSPACES = DATA / "workspaces"

DATABASE = DATA / "home.db"

APPS = ROOT / "apps"
