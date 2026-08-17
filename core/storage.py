from .config import *
from .db import init as init_db


def _migrate_documents_layout():
    """Workspaces created before the documents/media/appdata split have
    their content directly at <root>/ instead of <root>/documents/.
    Move it in place, once. Idempotent: skips any workspace that already
    has a documents/ subfolder, so this is safe to run on every boot."""

    if not WORKSPACES.is_dir():
        return

    for workspace_root in WORKSPACES.glob("*/*/*"):
        if not workspace_root.is_dir():
            continue

        documents_dir = workspace_root / "documents"

        if documents_dir.exists():
            continue

        entries = list(workspace_root.iterdir())

        if not entries:
            continue

        documents_dir.mkdir()

        for entry in entries:
            entry.rename(documents_dir / entry.name)


def init():

    DATA.mkdir(parents=True, exist_ok=True)
    WORKSPACES.mkdir(parents=True, exist_ok=True)

    _migrate_documents_layout()

    init_db()
