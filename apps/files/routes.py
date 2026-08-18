import shlex
import subprocess
from pathlib import Path

from flask import render_template, request, redirect, abort, url_for

from core import groups as core_groups
from core import sync_state
from core import workspaces as core_workspaces

from . import bp, NAME
from apps.ark.routes import ark_workspace
from apps.ark.runner import auto_sync, is_git_linked

FILES_HELP_INTRO = (
    "files works like a shell for this workspace - click to browse, or "
    "type real commands into the box below. cd/ls/pwd/cat/grep/find are "
    "read-only; mkdir/touch/mv/rm change things."
)

FILES_HELP = [
    ("cd PATH", "change directory (blank = workspace root)"),
    ("ls [PATH]", "list a directory - same as clicking, here for completeness"),
    ("pwd", "show the current path"),
    ("cat FILE", "print a file's contents"),
    ("grep PATTERN [PATH]", "search file contents recursively"),
    ("find NAME", "search filenames recursively"),
    ("mkdir NAME", "create a folder here"),
    ("touch NAME", "create an empty file here"),
    ("mv SRC DST", "move or rename something"),
    ("rm PATH", "delete a file, or an empty folder"),
    ("rm -r PATH", "delete a folder and everything in it"),
]

MUTATING_COMMANDS = {"mkdir", "touch", "mv", "rm"}

COMMAND_TIMEOUT = 10


def run_bin(argv, cwd):
    """Every non-cd command is a real coreutils binary, invoked with an
    explicit argv list (never shell=True) so there's no shell-metacharacter
    interpretation to worry about - shlex.split just tokenizes the typed
    command, it never hands anything to an actual shell interpreter. Every
    path-shaped argument is resolved through safe_path() before it ever
    reaches here, so containment/dotfile protection happens before, not
    after, a real process is spawned."""

    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 1, "", "timed out")


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


def do_ls(workspace, cwd, args):
    if len(args) > 1:
        return {"message": "ls takes at most one path", "is_error": True}

    argpath = args[0] if args else ""
    target = resolve_dir(workspace, cwd, argpath)

    if not target.is_dir():
        return {"message": f"{argpath or '.'} is not a directory", "is_error": True}

    result = run_bin(["ls", "-la", "."], cwd=str(target))

    if result.returncode != 0:
        return {"message": result.stderr.strip() or "ls failed", "is_error": True}

    return {"output": result.stdout}


def do_pwd(workspace, cwd, args):
    if args:
        return {"message": "pwd takes no arguments", "is_error": True}

    # A real pwd would print the server's actual disk path - not
    # meaningful (or safe to expose) to someone browsing a workspace, so
    # this one's just Python echoing back where they are in the
    # workspace, not a subprocess call.
    return {"output": ("/" + cwd) if cwd else "/"}


def do_cat(workspace, cwd, args):
    if len(args) != 1:
        return {"message": "cat needs exactly one file", "is_error": True}

    target = safe_path(workspace, f"{cwd}/{args[0]}")

    if not target.is_file():
        return {"message": f"{args[0]} is not a file", "is_error": True}

    result = run_bin(["cat", str(target)], cwd=str(workspace))

    if result.returncode != 0:
        return {"message": result.stderr.strip() or "cat failed", "is_error": True}

    text = result.stdout

    if len(text) > 200_000:
        text = text[:200_000] + "\n... (truncated)"

    return {"output": text}


def do_grep(workspace, cwd, args):
    if not args or len(args) > 2:
        return {"message": "grep needs a pattern and an optional path", "is_error": True}

    pattern = args[0]
    argpath = args[1] if len(args) > 1 else ""
    target = resolve_dir(workspace, cwd, argpath)

    if not target.is_dir():
        return {"message": f"{argpath or '.'} is not a directory", "is_error": True}

    # Search each non-dotfile top-level entry by name, not "." itself -
    # --exclude-dir=.* matches "." too, which would silently exclude the
    # entire search root and make every grep look like "no matches".
    children = sorted(c.name for c in target.iterdir() if not c.name.startswith("."))

    if not children:
        return {"message": "no matches", "is_error": False}

    result = run_bin(
        ["grep", "-rniI", "--exclude-dir=.*", "--exclude=.*", "-e", pattern, *children],
        cwd=str(target),
    )

    # grep exits 1 for "no matches", not an error - only >=2 is real trouble.
    if result.returncode not in (0, 1):
        return {"message": result.stderr.strip() or "grep failed", "is_error": True}

    lines = [l for l in result.stdout.splitlines() if l]

    if not lines:
        return {"message": "no matches", "is_error": False}

    base = to_relpath(workspace, target)
    entries = []

    for line in lines[:200]:
        parts = line.split(":", 2)

        if len(parts) != 3:
            continue

        rel, lineno, content = parts
        rel = rel[2:] if rel.startswith("./") else rel
        full_rel = f"{base}/{rel}" if base else rel

        entries.append({
            "name": Path(rel).name,
            "relpath": full_rel,
            "is_dir": False,
            "detail": f"line {lineno}: {content.strip()[:160]}",
        })

    return {"entries": entries, "find": pattern}


def do_find(workspace, cwd, args):
    if len(args) != 1:
        return {"message": "find needs exactly one name", "is_error": True}

    name = args[0]
    target = resolve_dir(workspace, cwd, "")

    result = run_bin(["find", ".", "-iname", f"*{name}*"], cwd=str(target))

    if result.returncode != 0:
        return {"message": result.stderr.strip() or "find failed", "is_error": True}

    base = to_relpath(workspace, target)
    entries = []

    for line in result.stdout.splitlines():
        if not line or line == ".":
            continue

        rel = line[2:] if line.startswith("./") else line

        if any(part.startswith(".") for part in Path(rel).parts):
            continue

        full_rel = f"{base}/{rel}" if base else rel

        entries.append({
            "name": Path(rel).name,
            "relpath": full_rel,
            "is_dir": (target / rel).is_dir(),
        })

    entries.sort(key=lambda e: (not e["is_dir"], e["relpath"].lower()))

    if not entries:
        return {"message": "no matches", "is_error": False}

    return {"entries": entries}


def do_mkdir(workspace, cwd, args):
    if len(args) != 1:
        return {"message": "mkdir needs exactly one name", "is_error": True}

    target = safe_path(workspace, f"{cwd}/{args[0]}")

    if target.exists():
        return {"message": f"{args[0]} already exists", "is_error": True}

    result = run_bin(["mkdir", str(target)], cwd=str(workspace))

    if result.returncode != 0:
        return {"message": result.stderr.strip() or "mkdir failed", "is_error": True}

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

    result = run_bin(["touch", str(target)], cwd=str(workspace))

    if result.returncode != 0:
        return {"message": result.stderr.strip() or "touch failed", "is_error": True}

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

    result = run_bin(["mv", str(src), str(dst)], cwd=str(workspace))

    if result.returncode != 0:
        return {"message": result.stderr.strip() or "mv failed", "is_error": True}

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
            argv = ["rm", "-r", str(target)]
        elif any(target.iterdir()):
            return {"message": f"{target_args[0]} isn't empty - use rm -r", "is_error": True}
        else:
            argv = ["rmdir", str(target)]
    else:
        argv = ["rm", str(target)]

    result = run_bin(argv, cwd=str(workspace))

    if result.returncode != 0:
        return {"message": result.stderr.strip() or "rm failed", "is_error": True}

    return {"message": f"deleted {target_args[0]}"}


COMMAND_HANDLERS = {
    "ls": do_ls,
    "pwd": do_pwd,
    "cat": do_cat,
    "grep": do_grep,
    "find": do_find,
    "mkdir": do_mkdir,
    "touch": do_touch,
    "mv": do_mv,
    "rm": do_rm,
}


def entry_links(entries, workspace_id, cwd, find=None):
    """Attaches an `href` to each listing/search-result entry - a folder
    navigates within Files, a file hands off to the shared Editor app,
    carrying enough context (app/home) for Editor's topbar and close
    button to point back at the exact directory being browsed here.

    Editor's own workspace root is the same true workspace root Files
    browses from (see apps.editor.routes.editor_workspace), so a file's
    relpath here needs no adjustment - it means the same thing to both."""

    home = url_for("files.browse", workspace=workspace_id, path=cwd)

    for entry in entries:
        if entry["is_dir"]:
            entry["href"] = url_for("files.browse", workspace=workspace_id, path=entry["relpath"])
        else:
            editor_kwargs = dict(
                file=entry["relpath"],
                workspace=workspace_id,
                app="Files",
                home=home,
            )

            if find:
                editor_kwargs["find"] = find

            entry["href"] = url_for("editor.view", **editor_kwargs)

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
    is_search = False
    command_output = None
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
                    command_output = result.get("output")

                    if "entries" in result:
                        is_search = True
                        entries = entry_links(
                            result["entries"], record["id"], cwd, find=result.get("find"),
                        )

                    if not is_error and first in MUTATING_COMMANDS:
                        auto_sync(workspace, record["id"], force=True)

            else:
                message, is_error = f"unknown command: {first}", True

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
        command_output=command_output,
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
