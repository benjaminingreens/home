from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA = Path("/var/lib/home")

DATABASE = DATA / "home.db"

WORKSPACES = DATA / "workspaces"

APPS = ROOT / "apps"
