import shlex
import shutil
from pathlib import Path

from flask import render_template, request, redirect, abort, url_for

from core import groups as core_groups
from core import sync_state

from . import bp, NAME
from apps.ark.routes import ark_workspace
from apps.ark.runner import auto_sync, is_git_linked

FILES_HELP_INTRO = (
    "files is a generic browser for everything in this workspace - click "
    "a folder to open it, click a file to view/edit it. the command box "
    "is for anything that isn't just looking: creating, moving, "
    "deleting, or searching by filename."
)

FILES_HELP = [
    ("mkdir NAME", "create a folder here"),
    ("touch NAME", "create an empty file here"),
    ("mv SRC DST", "move or rename something"),
    ("rm PATH", "delete a file, or an empty folder"),
    ("rm -r PATH", "delete a folder and everything in it"),
    ("<text>", "search filenames anywhere in this workspace"),
]

MUTATING_COMMANDS = {"mkdir", "touch", "mv", "rm"}


def safe_path(workspace, relpath):
    """Resolves relpath under workspace, mirroring apps.ark.routes'
    safe_file containment check, plus a guard Files specifically needs:
    reject any dotfile/dir segment (.ark, .git, any future dotfile) -
    those live directly inside the same per-app data root Files browses,
    and must never be listed, opened, or mutated by a generic browser."""

    relpath = (relpath or "").strip().strip("/")
    target = (workspace / relpath).resolve() if relpath else workspace.resolve()
    root = workspace.resolve()

    if root not in target.parents and target != root:
        abort(403)

    for part in (Path(relpath).parts if relpath else []):
        if part.startswith("."):
            abort(403)

    return target


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


def search_files(workspace, query):
    query = query.lower()
    matches = []

    for child in workspace.rglob("*"):
        rel = child.relative_to(workspace)

        if any(part.startswith(".") for part in rel.parts):
            continue

        if query in child.name.lower():
            matches.append({
                "name": child.name,
                "relpath": str(rel),
                "is_dir": child.is_dir(),
                "size": child.stat().st_size if child.is_file() else None,
            })

    matches.sort(key=lambda e: (not e["is_dir"], e["relpath"].lower()))

    return matches


def build_breadcrumbs(relpath):
    parts = [p for p in relpath.split("/") if p] if relpath else []
    crumbs = []
    accum = []

    for part in parts:
        accum.append(part)
        crumbs.append({"name": part, "path": "/".join(accum)})

    return crumbs


def run_command(workspace, cwd, tokens):
    """tokens is already shlex-split, non-empty, first token lowercased
    and confirmed to be in MUTATING_COMMANDS by the caller. Returns
    (message, is_error)."""

    cmd, args = tokens[0], tokens[1:]

    if cmd == "mkdir":
        if len(args) != 1:
            return "mkdir needs exactly one name", True

        target = safe_path(workspace, f"{cwd}/{args[0]}")

        if target.exists():
            return f"{args[0]} already exists", True

        target.mkdir()

        return f"created {args[0]}/", False

    if cmd == "touch":
        if len(args) != 1:
            return "touch needs exactly one name", True

        target = safe_path(workspace, f"{cwd}/{args[0]}")

        if target.exists():
            return f"{args[0]} already exists", True

        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        return f"created {args[0]}", False

    if cmd == "mv":
        if len(args) != 2:
            return "mv needs a source and a destination", True

        src = safe_path(workspace, f"{cwd}/{args[0]}")
        dst = safe_path(workspace, f"{cwd}/{args[1]}")

        if src == workspace.resolve():
            return "can't move the workspace root", True

        if not src.exists():
            return f"{args[0]} doesn't exist", True

        if dst.exists():
            return f"{args[1]} already exists", True

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

        return f"moved {args[0]} -> {args[1]}", False

    if cmd == "rm":
        recursive = args and args[0] == "-r"
        target_args = args[1:] if recursive else args

        if len(target_args) != 1:
            return "rm [-r] needs exactly one path", True

        target = safe_path(workspace, f"{cwd}/{target_args[0]}")

        if target == workspace.resolve():
            return "can't delete the workspace root", True

        if not target.exists():
            return f"{target_args[0]} doesn't exist", True

        if target.is_dir():
            if recursive:
                shutil.rmtree(target)
            elif any(target.iterdir()):
                return f"{target_args[0]} isn't empty - use rm -r", True
            else:
                target.rmdir()
        else:
            target.unlink()

        return f"deleted {target_args[0]}", False

    return f"unknown command: {cmd}", True


def entry_links(entries, workspace_id, cwd):
    """Attaches an `href` to each listing/search-result entry - a folder
    navigates within Files, a file hands off to the shared Editor app,
    carrying enough context (app/home) for Editor's topbar and close
    button to point back at the exact directory being browsed here."""

    home = url_for("files.browse", workspace=workspace_id, path=cwd)

    for entry in entries:
        if entry["is_dir"]:
            entry["href"] = url_for("files.browse", workspace=workspace_id, path=entry["relpath"])
        else:
            entry["href"] = url_for(
                "editor.view",
                file=entry["relpath"],
                workspace=workspace_id,
                app="Files",
                home=home,
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

    user, workspace, record = ark_workspace(workspace_id)

    if not user:
        return redirect("/login")

    # Opportunistic pull-and-push on every visit, same as Ark/Files'
    # shared workspace - see apps.ark.runner.auto_sync's docstring.
    auto_sync(workspace, record["id"])
    conflict = sync_state.is_conflicted(record["id"])

    message = ""
    is_error = False
    help_commands = None
    is_search = False
    entries = []

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

            if first in MUTATING_COMMANDS:
                if conflict:
                    message, is_error = "workspace has a sync conflict - resolve it first", True
                else:
                    message, is_error = run_command(workspace, cwd, [first] + tokens[1:])

                    if not is_error:
                        auto_sync(workspace, record["id"], force=True)
            else:
                is_search = True
                entries = entry_links(search_files(workspace, query), record["id"], cwd)
                message = "" if entries else "no matches"

    if not is_search:
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
        is_search=is_search,
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
        workspace_options=core_groups.list_group_workspaces(record["group_id"], "ark"),
        active_workspace_id=record["id"],
    )
