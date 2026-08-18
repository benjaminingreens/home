from .config import *
from .db import init as init_db


def _migrate_app_data_layout():
    """A workspace's user-facing data lives at <root>/<app>/ (e.g.
    .../ark/myworkspace/ark/), not directly at <root>/. Two older layouts
    need folding into that, once each, in place:
      - the original pre-split layout, content sitting directly at
        <root>/;
      - the short-lived documents/media/appdata split, content at
        <root>/documents/ regardless of which app owned it.
    Idempotent: skips any workspace that already has its <app>/ folder,
    so this is safe to run on every boot."""

    if not WORKSPACES.is_dir():
        return

    for workspace_root in WORKSPACES.glob("*/*/*"):
        if not workspace_root.is_dir():
            continue

        app = workspace_root.parent.name
        data_dir = workspace_root / app

        if data_dir.exists():
            continue

        documents_dir = workspace_root / "documents"

        if documents_dir.exists():
            documents_dir.rename(data_dir)
            continue

        entries = list(workspace_root.iterdir())

        if not entries:
            continue

        data_dir.mkdir()

        for entry in entries:
            entry.rename(data_dir / entry.name)


def init():

    DATA.mkdir(parents=True, exist_ok=True)
    WORKSPACES.mkdir(parents=True, exist_ok=True)

    _migrate_app_data_layout()

    init_db()
