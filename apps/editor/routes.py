from pathlib import Path
from urllib.parse import urlencode

from flask import render_template, request, redirect, abort

from core.auth import current_user
from core import workspaces as core_workspaces
from core import groups as core_groups
from core import locks as core_locks
from core import sync_state

from . import bp, NAME
from apps.ark.runner import auto_sync

CONFLICT_MESSAGE = "workspace has a sync conflict - resolve it first"


def editor_workspace(workspace_id):
    """Editor has no "active workspace" of its own - every caller (Ark,
    Files, anything else) must hand it an explicit workspace_id. Resolved
    off the workspace row's own `app` column rather than a hardcoded
    "ark", so this stays reusable for any future app's workspaces, not
    just Ark's. Returns the true workspace root (matching Files, which
    shares the same underlying data), not just the app's own data folder
    one level below it - a file= path is relative to that same root
    everywhere a caller links into Editor from."""

    user = current_user()

    if not user:
        return None, None, None

    record = core_groups.get_workspace(int(workspace_id))

    if not record or not core_groups.require_active_member(user["id"], record["group_id"]):
        abort(403)

    workspace = core_workspaces.root(record["group_slug"], record["app"], record["name"])

    return user, workspace, record


def safe_file(workspace, relpath):
    """Mirrors apps.files.routes.safe_path's containment + dotfile guard -
    Editor's root is now the true workspace root (see editor_workspace()),
    so without this, a crafted file= could reach into an app's own .ark/
    or .git/ internals the same way an unguarded Files browse could."""

    relpath = (relpath or "").strip().strip("/")
    target = (workspace / relpath).resolve() if relpath else workspace.resolve()
    root = workspace.resolve()

    if root not in target.parents and target != root:
        abort(403)

    for part in (Path(relpath).parts if relpath else []):
        if part.startswith("."):
            abort(403)

    return target


@bp.get("/")
def view():
    workspace_id = request.args.get("workspace")
    file_path = request.args.get("file")

    if not workspace_id or not file_path:
        return redirect("/")

    user, workspace, record = editor_workspace(workspace_id)

    if not user:
        return redirect("/login")

    auto_sync(workspace, record["id"])
    conflict = sync_state.is_conflicted(record["id"])

    target = safe_file(workspace, file_path)

    file_content = ""
    if target.exists() and target.is_file():
        file_content = target.read_text(encoding="utf-8", errors="replace")

    file_lines = file_content.split("\n")

    find = request.args.get("find", "")
    highlight_line = None

    if find:
        for i, line in enumerate(file_lines):
            if find in line:
                highlight_line = i
                break

    lock_user_id, lock_username = core_locks.holder(record["id"], file_path)
    locked_by = lock_username if lock_user_id and lock_user_id != user["id"] else None

    return render_template(
        "editor.html",
        page_class="editor",
        file_path=file_path,
        file_content=file_content,
        file_lines=file_lines,
        highlight_line=highlight_line,
        locked_by=locked_by,
        conflict=conflict,
        user=user,
        app_label=request.args.get("app", NAME),
        app_home=request.args.get("home", "/"),
        workspace_id=record["id"],
    )


@bp.post("/save")
def save():
    workspace_id = request.form.get("workspace")
    user, workspace, record = editor_workspace(workspace_id)

    if not user:
        return redirect("/login")

    relpath = request.form.get("path", "")
    content = request.form.get("content", "")

    if sync_state.is_conflicted(record["id"]):
        # Don't write into a workspace mid-resolution - the typed content
        # is still safe in the browser's textarea either way (autosave
        # just retries later), this only refuses to persist it yet.
        return {"ok": False, "error": CONFLICT_MESSAGE}, 409

    # A save implies an active edit session - (re)claim the lock as a
    # heartbeat so it doesn't go stale mid-edit. Doesn't block the save
    # itself on lock ownership: this is a small trusted-group tool, not an
    # adversarial one, and refusing to persist someone's typed text because
    # of a lock race would be worse than the rare double-edit it prevents.
    core_locks.acquire(record["id"], relpath, user["id"])

    target = safe_file(workspace, relpath)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    auto_sync(workspace, record["id"], force=True)

    qs = urlencode({
        "file": relpath,
        "workspace": workspace_id,
        "app": request.form.get("app", NAME),
        "home": request.form.get("home", "/"),
    })

    return redirect(f"/apps/editor/?{qs}")


@bp.post("/lock")
def lock_file():
    user = current_user()

    if not user:
        return {"ok": False}, 401

    workspace_id = request.form.get("workspace", type=int)
    path = request.form.get("path", "")

    if not workspace_id or not path:
        return {"ok": False}, 400

    ok, holder_name = core_locks.acquire(workspace_id, path, user["id"])

    if ok:
        return {"ok": True}

    return {"ok": False, "holder": holder_name}, 409


@bp.post("/unlock")
def unlock_file():
    user = current_user()

    if not user:
        return {"ok": False}, 401

    workspace_id = request.form.get("workspace", type=int)
    path = request.form.get("path", "")

    if workspace_id and path:
        core_locks.release(workspace_id, path, user["id"])

    return {"ok": True}
