import shlex
import shutil
from pathlib import Path

from flask import render_template, request, redirect, abort, url_for

from core import sync_state
from core import workspaces as core_workspaces

from . import bp, NAME
from apps.ark.routes import ark_workspace
from apps.ark.runner import auto_sync, is_git_linked

FILES_HELP_INTRO = (
    "files browses this workspace - click to navigate, or type a command "
    "below for the few things clicking can't do."
)

FILES_HELP = [
    ("cd PATH", "change directory (blank = workspace root)"),
    ("mkdir NAME", "create a folder here"),
    ("touch NAME", "create an empty file here"),
    ("mv SRC DST", "move or rename something"),
    ("rm PATH", "delete a file, or an empty folder"),
    ("rm -r PATH", "delete a folder and everything in it"),
]

MUTATING_COMMANDS = {"mkdir", "touch", "mv", "rm"}


def safe_path(workspace, relpath):
    """Resolves relpath under workspace, mirroring apps.ark.routes'
    safe_file containment check, plus a guard Files specifically needs:
    reject any dotfile/dir segment (.ark, .git, any future dotfile) -
    those live inside the app's own data folder under this same
    workspace root, and must never be listed, opened, or mutated by a
    generic browser."""

    relpath = (relpath or "").strip().strip("/")
    target = (workspace / relpath).resolve() if relpath else workspace.resolve()
    root = workspace.resolve()

    if root not in target.parents and target != root:
        abort(403)

    for part in (Path(relpath).parts if relpath else []):
        if part.startswith("."):
            abort(403)

    return target


def resolve_dir(workspace, cwd, argpath):
    combined = f"{cwd}/{argpath}" if argpath else cwd
    return safe_path(workspace, combined)


def to_relpath(workspace, target):
    rel = target.relative_to(workspace.resolve())
    return "" if str(rel) == "." else str(rel)


def list_dir(workspace, relpath):
    target = safe_path(workspace, relpath)

    if not target.is_dir():
        abort(404)

    entries = []

    for child in target.iterdir():
        if child.name.startswith("."):
            continue

        entries.append({
            "name": child.name,
            "relpath": str(child.relative_to(workspace)),
            "is_dir": child.is_dir(),
            "size": child.stat().st_size if child.is_file() else None,
        })

    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))

    return entries


def build_breadcrumbs(relpath):
    parts = [p for p in relpath.split("/") if p] if relpath else []
    crumbs = []
    accum = []

    for part in parts:
        accum.append(part)
        crumbs.append({"name": part, "path": "/".join(accum)})

    return crumbs


def do_mkdir(workspace, cwd, args):
    if len(args) != 1:
        return {"message": "mkdir needs exactly one name", "is_error": True}

    target = safe_path(workspace, f"{cwd}/{args[0]}")

    if target.exists():
        return {"message": f"{args[0]} already exists", "is_error": True}

    target.mkdir(parents=True)

    return {"message": f"created {args[0]}/"}


def do_touch(workspace, cwd, args):
    if len(args) != 1:
        return {"message": "touch needs exactly one name", "is_error": True}

    target = safe_path(workspace, f"{cwd}/{args[0]}")

    if target.exists():
        return {"message": f"{args[0]} already exists", "is_error": True}

    # Real touch won't create missing parent directories - this app's
    # convention (matching Editor's save()) is that naming a file under a
    # not-yet-existing folder just creates the folder too.
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()

    return {"message": f"created {args[0]}"}


def do_mv(workspace, cwd, args):
    if len(args) != 2:
        return {"message": "mv needs a source and a destination", "is_error": True}

    src = safe_path(workspace, f"{cwd}/{args[0]}")
    dst = safe_path(workspace, f"{cwd}/{args[1]}")

    if src == workspace.resolve():
        return {"message": "can't move the workspace root", "is_error": True}

    if not src.exists():
        return {"message": f"{args[0]} doesn't exist", "is_error": True}

    if dst.exists():
        return {"message": f"{args[1]} already exists", "is_error": True}

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

    return {"message": f"moved {args[0]} -> {args[1]}"}


def do_rm(workspace, cwd, args):
    recursive = bool(args) and args[0] == "-r"
    target_args = args[1:] if recursive else args

    if len(target_args) != 1:
        return {"message": "rm [-r] needs exactly one path", "is_error": True}

    target = safe_path(workspace, f"{cwd}/{target_args[0]}")

    if target == workspace.resolve():
        return {"message": "can't delete the workspace root", "is_error": True}

    if not target.exists():
        return {"message": f"{target_args[0]} doesn't exist", "is_error": True}

    if target.is_dir():
        if recursive:
            shutil.rmtree(target)
        elif any(target.iterdir()):
            return {"message": f"{target_args[0]} isn't empty - use rm -r", "is_error": True}
        else:
            target.rmdir()
    else:
        target.unlink()

    return {"message": f"deleted {target_args[0]}"}


COMMAND_HANDLERS = {
    "mkdir": do_mkdir,
    "touch": do_touch,
    "mv": do_mv,
    "rm": do_rm,
}


def entry_links(entries, workspace_id, cwd):
    """Attaches an `href` to each listing entry - a folder navigates
    within Files, a file hands off to the shared Editor app, carrying
    enough context (app/home) for Editor's topbar and close button to
    point back at the exact directory being browsed here.

    Editor's own workspace root is the same true workspace root Files
    browses from (see apps.editor.routes.editor_workspace), so a file's
    relpath here needs no adjustment - it means the same thing to both."""

    home = url_for("files.browse", workspace=workspace_id, path=cwd)

    for entry in entries:
        if entry["is_dir"]:
            entry["href"] = url_for("files.browse", workspace=workspace_id, path=entry["relpath"])
        else:
            entry["href"] = url_for(
                "editor.view", file=entry["relpath"], workspace=workspace_id, app="Files", home=home,
            )

    return entries


@bp.route("/", methods=["GET", "POST"])
def browse():
    if request.method == "POST":
        workspace_id = request.form.get("workspace")
        cwd = request.form.get("path", "")
    else:
        workspace_id = request.args.get("workspace")
        cwd = request.args.get("path", "")

    user, _, record = ark_workspace(workspace_id)

    if not user:
        return redirect("/login")

    # Files browses the true workspace root - one level above the app's
    # own data folder (e.g. .../ark/), so that folder shows up as a
    # regular, clickable entry instead of being silently skipped past.
    # git's scope is this same root (see core.workspaces.hoist_git_to_root),
    # so auto_sync/is_git_linked operate directly on `workspace` too.
    workspace = core_workspaces.root(record["group_slug"], record["app"], record["name"])

    # Opportunistic pull-and-push on every visit, same as Ark/Files'
    # shared workspace - see apps.ark.runner.auto_sync's docstring.
    auto_sync(workspace, record["id"])
    conflict = sync_state.is_conflicted(record["id"])

    message = ""
    is_error = False
    help_commands = None

    if request.method == "POST":
        query = request.form.get("query", "").strip()

        if query.startswith("/"):
            command = query[1:].strip().lower()

            if command == "home":
                return redirect("/")

            if command == "help":
                help_commands = FILES_HELP
            else:
                message, is_error = f"unknown command: /{command}", True

        elif query:
            tokens = shlex.split(query)
            first = tokens[0].lower() if tokens else ""
            rest = tokens[1:]

            if first == "cd":
                if len(rest) > 1:
                    message, is_error = "cd takes at most one path", True
                else:
                    target = resolve_dir(workspace, cwd, rest[0] if rest else "")

                    if not target.is_dir():
                        message, is_error = f"{rest[0] if rest else '.'} is not a directory", True
                    else:
                        cwd = to_relpath(workspace, target)

            elif first in COMMAND_HANDLERS:
                if conflict and first in MUTATING_COMMANDS:
                    message, is_error = "workspace has a sync conflict - resolve it first", True
                else:
                    result = COMMAND_HANDLERS[first](workspace, cwd, rest)
                    message = result.get("message", "")
                    is_error = result.get("is_error", False)

                    if not is_error and first in MUTATING_COMMANDS:
                        auto_sync(workspace, record["id"], force=True)

            else:
                message, is_error = f"unknown command: {first}", True

    entries = entry_links(list_dir(workspace, cwd), record["id"], cwd)

    if cwd:
        parent = cwd.rsplit("/", 1)[0] if "/" in cwd else ""
        entries = [{
            "name": "..",
            "relpath": parent,
            "is_dir": True,
            "size": None,
            "href": url_for("files.browse", workspace=record["id"], path=parent),
        }] + entries

    return render_template(
        "files_home.html",
        page_class="results" if entries else "",
        path=cwd,
        breadcrumbs=build_breadcrumbs(cwd),
        entries=entries,
        message=message,
        is_error=is_error,
        help_commands=help_commands,
        help_intro=(FILES_HELP_INTRO if help_commands else None),
        conflict=conflict,
        user=user,
        app_label=NAME,
        app_home="/apps/files/",
        workspace_id=record["id"],
        git_linked=is_git_linked(workspace),
        active_workspace_id=record["id"],
    )
