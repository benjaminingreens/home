from urllib.parse import urlencode

from flask import render_template, request, redirect, abort

from core.auth import current_user
from core import workspaces as core_workspaces
from core import groups as core_groups
from core import locks as core_locks
from core import sync_state

from . import bp, NAME
from .runner import install, run, add, is_git_linked, auto_sync, theirs_content, resolve_conflict
from .parser import highlight_meta


def resolve_active_workspace(user):
    """The DB workspace row backing wherever this user's Ark terminal is
    currently pointed. Falls back to (and lazily creates) their personal
    group's "default" workspace record on first use - the record itself
    doesn't touch disk; that only happens through the choose/link setup
    flow, same as before groups existed."""

    workspace_id = user["active_workspace_id"]

    if workspace_id:
        record = core_groups.get_workspace(workspace_id)

        if record and core_groups.require_active_member(user["id"], record["group_id"]):
            return record

    record = core_groups.get_or_create_default_workspace(user["id"], "ark")
    core_groups.set_active_workspace(user["id"], record["id"])

    return record


def resolve_workspace(user, workspace_id=None):
    """A specific workspace by id, checking the user is actually an active
    member of the group that owns it - not just whichever workspace is
    currently "active" in the terminal. Needed anywhere (e.g. a Documents
    result link) that points at a workspace that isn't necessarily the
    active one; using the active workspace unconditionally here was the
    bug where clicking a shared-workspace note opened a same-named file
    from the viewer's own personal workspace instead."""

    if workspace_id is None:
        return resolve_active_workspace(user)

    record = core_groups.get_workspace(int(workspace_id))

    if not record or not core_groups.require_active_member(user["id"], record["group_id"]):
        abort(403)

    return record


def ark_workspace(workspace_id=None):
    user = current_user()

    if not user:
        return None, None, None

    record = resolve_workspace(user, workspace_id)
    workspace = core_workspaces.path(record["group_slug"], "ark", record["name"])

    return user, workspace, record


def workspace_ready(workspace):
    return (workspace / ".ark").exists()


def safe_file(workspace, relpath):
    relpath = relpath.strip() or "note/inbox.txt"
    target = (workspace / relpath).resolve()

    if workspace.resolve() not in target.parents and target != workspace.resolve():
        abort(403)

    return target


def new_file_path(relpath):
    """Where a bare "new <file>" should land. inbox.txt is Ark's own
    canonical root file (tidy later sorts it into note/todo/evnt), so it
    stays at the workspace root; anything else without an explicit
    note/todo/evnt prefix defaults into note/, since Ark's scanner never
    looks at the workspace root otherwise."""

    relpath = relpath.strip()

    if not relpath:
        return None

    top = relpath.split("/", 1)[0]

    if top not in ("note", "todo", "evnt") and relpath != "inbox.txt":
        relpath = f"note/{relpath}"

    return relpath


def create_new_file(workspace, relpath):
    target = safe_file(workspace, relpath)
    target.parent.mkdir(parents=True, exist_ok=True)

    if not target.exists():
        target.write_text("", encoding="utf-8")

    return target


ARK_HELP_INTRO = (
    "ark is your personal notes and task repository. jot down notes, "
    "todos, and events as plain text - they're kept organized and synced "
    "automatically."
)

ARK_HELP = [
    ("/note: <text>", "save a quick note"),
    ("/todo: <text>", "save a task"),
    ("/evnt: <text>", "save an event"),
    ("tidy", "sort inbox into note/todo/evnt (dry run - shows what would move)"),
    ("/tidy", "same, but actually applies the changes"),
    ("/new <file>", "create a file"),
    ("/home", "go to the home screen"),
    ("/help", "this message"),
]

CONFLICT_MESSAGE = "workspace has a sync conflict - resolve it first"


def process(workspace, workspace_id, query):
    """Returns (added, records, message, is_error, help_commands) -
    help_commands is None outside the /help path, which render.html
    renders via the shared _help.html partial instead of stuffing curated
    text into the generic `message` string. is_error marks messages that
    mean "that didn't work" (unknown command, blocked by a conflict, an
    Ark-reported error) so the template can style them differently from
    an ordinary result.

    A leading "/" marks a HOME system command (help, tidy --apply,
    note:/todo:/evnt: quick-add); anything else is handed straight to
    Ark's own query engine untouched, including a bare "tidy" (real Ark
    CLI dry-run behavior). note:/todo:/evnt: live behind the slash too,
    not because Ark's CLI has a real "add" command it maps onto (it
    doesn't - add() just appends straight to inbox.txt), but because
    that's exactly why they can't be bare: there's no Ark-native meaning
    for them to defer to, so leaving them unprefixed would silently
    intercept text a bare query was supposed to hand untouched to Ark.
    This is the boundary that keeps HOME's shortcuts from colliding with
    Ark's own command/query namespace.

    Syncing itself isn't a command any more - it happens automatically
    (see auto_sync, called by the route around every request) - but
    mutating commands here refuse to run while the workspace is flagged
    conflicted, since writing more local changes on top of an unresolved
    conflict only makes the resolution screen harder to reason about."""

    query = query.strip()

    if not query:
        return False, [], "", False, None

    if query.startswith("/"):
        command = query[1:].strip()
        lower = command.lower()

        if lower == "help":
            return False, [], "", False, ARK_HELP

        if lower == "tidy":
            if sync_state.is_conflicted(workspace_id):
                return False, [], CONFLICT_MESSAGE, True, None

            _, stdout, error = run(workspace, "tidy --apply")
            auto_sync(workspace, workspace_id, force=True)
            return False, [], error or stdout or "nothing to tidy", bool(error), None

        if command.startswith(("note:", "todo:", "evnt:")):
            if sync_state.is_conflicted(workspace_id):
                return False, [], CONFLICT_MESSAGE, True, None

            add(workspace, command)
            auto_sync(workspace, workspace_id, force=True)
            return True, [], "added", False, None

        return False, [], f"unknown command: /{lower}", True, None

    records, stdout, error = run(workspace, query)

    if error:
        return False, [], error, True, None

    if records:
        return False, records, "", False, None

    if stdout:
        return False, [], stdout, False, None

    return False, [], "no results", False, None


@bp.route("/", methods=["GET", "POST"])
def home():
    file_path = request.args.get("file")
    workspace_id = request.args.get("workspace") if file_path else None

    user, workspace, record = ark_workspace(workspace_id)

    if not user:
        return redirect("/login")

    if not file_path and not workspace_ready(workspace):
        return redirect("/apps/ark/workspace")

    # Opportunistic pull-and-push on every visit - pulls whatever anyone
    # else has pushed since, and pushes anything committed locally (e.g.
    # by a prior save/add/tidy) that hasn't gone out yet. Best-effort: a
    # no-op if unlinked, offline, or already flagged conflicted. Throttled
    # (see core.sync_state) so a workspace only actually gets checked once
    # per few seconds, no matter how many people load this page at once.
    auto_sync(workspace, record["id"])
    conflict = sync_state.is_conflicted(record["id"])

    if file_path:
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
            "file.html",
            page_class="editor",
            file_path=file_path,
            file_content=file_content,
            file_lines=[highlight_meta(l) for l in file_lines],
            highlight_line=highlight_line,
            locked_by=locked_by,
            conflict=conflict,
            user=user,
            app_label=request.args.get("app", NAME),
            app_home=request.args.get("home", "/apps/ark/"),
            workspace_id=record["id"],
        )

    records = []
    query = ""
    message = "added" if request.args.get("added") else ""
    is_error = False
    help_commands = None

    if request.method == "POST":
        query = request.form.get("query", "").strip()

        if query:

            if query.startswith("/"):
                command = query[1:].strip()
                cmd_lower = command.lower()

                if cmd_lower == "home":
                    return redirect("/")

                if cmd_lower.startswith("new "):
                    if conflict:
                        message, is_error = CONFLICT_MESSAGE, True
                    else:
                        relpath = new_file_path(command[4:])

                        if relpath:
                            create_new_file(workspace, relpath)
                            auto_sync(workspace, record["id"], force=True)
                            return redirect(f"/apps/ark/?file={relpath}")

                        return redirect("/apps/ark/")

            if not message:
                added, records, message, is_error, help_commands = process(workspace, record["id"], query)

                if added:
                    return redirect("/apps/ark/?added=1")

    # Idle state (just opened the app, nothing typed/shown yet) defaults
    # to showing help - about + commands - instead of a blank screen.
    if not query and not message and not records:
        help_commands = ARK_HELP

    page_class = "results" if records else ""

    return render_template(
        "home.html",
        page_class=page_class,
        query=query,
        records=records,
        message=message,
        is_error=is_error,
        help_commands=help_commands,
        help_intro=(ARK_HELP_INTRO if help_commands else None),
        conflict=conflict,
        user=user,
        app_label=NAME,
        app_home="/apps/ark/",
        apps=[],
        git_linked=is_git_linked(workspace),
        workspace_options=core_groups.list_group_workspaces(record["group_id"], "ark"),
        active_workspace_id=record["id"],
    )


@bp.post("/workspaces")
def switch_workspace():
    """The topbar dropdown posts here. Creating workspaces lives in
    Settings, next to the group it belongs to - this endpoint only
    switches which existing one the terminal is pointed at."""

    user = current_user()

    if not user:
        return redirect("/login")

    try:
        core_groups.set_active_workspace(user["id"], int(request.form.get("workspace_id", 0)))
    except (ValueError, PermissionError):
        pass

    return redirect("/apps/ark/")


@bp.route("/workspace", methods=["GET", "POST"])
def workspace_setup():
    user, workspace, record = ark_workspace()

    if not user:
        return redirect("/login")

    group_slug = record["group_slug"]
    workspace_name = record["name"]
    error = ""
    message = ""

    if request.method == "POST":
        action = request.form.get("action")

        if action == "new":
            install(workspace)
            return redirect("/apps/ark/")

        elif action == "start_link":
            core_workspaces.start_link(group_slug, "ark", workspace_name)

        elif action == "finish_link":
            try:
                core_workspaces.finish_link(group_slug, "ark", workspace_name)
                return redirect("/apps/ark/")
            except ValueError as e:
                error = str(e)

        elif action == "enable_git":
            try:
                core_workspaces.enable_git(group_slug, "ark", workspace_name)
                message = "local sync enabled"
            except ValueError as e:
                error = str(e)

    ready = workspace_ready(workspace)
    linked = is_git_linked(workspace)
    bare_started = core_workspaces.has_bare_repo(group_slug, "ark", workspace_name)

    if not ready:
        state = "linking" if bare_started else "choose"
    elif not linked:
        state = "upgrade"
    else:
        state = "linked"

    if linked:
        remote = (
            core_workspaces.current_remote(group_slug, "ark", workspace_name)
            or core_workspaces.remote_url(group_slug, "ark", workspace_name)
        )
    elif bare_started:
        remote = core_workspaces.remote_url(group_slug, "ark", workspace_name)
    else:
        remote = None

    return render_template(
        "workspace.html",
        user=user,
        app_label=NAME,
        app_home="/apps/ark/",
        state=state,
        remote=remote,
        error=error,
        message=message,
        workspace_label=f"{record['group_name']} / {record['name']}",
        workspace_options=core_groups.list_group_workspaces(record["group_id"], "ark"),
        active_workspace_id=record["id"],
    )


@bp.post("/save")
def save():
    workspace_id = request.form.get("workspace")
    user, workspace, record = ark_workspace(workspace_id)

    if not user:
        return redirect("/login")

    relpath = request.form.get("path", "note/inbox.txt")
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

    qs = urlencode({"file": relpath, **({"workspace": workspace_id} if workspace_id else {})})

    return redirect(f"/apps/ark/?{qs}")


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


@bp.route("/conflicts", methods=["GET", "POST"])
def conflicts():
    workspace_id = request.values.get("workspace")
    user, workspace, record = ark_workspace(workspace_id)

    if not user:
        return redirect("/login")

    state = sync_state.get(record["id"])

    if state["status"] != "conflict":
        return redirect("/apps/ark/")

    if request.method == "POST":

        if request.form.get("version", type=int) != state["version"]:
            return redirect(f"/apps/ark/conflicts?workspace={record['id']}&stale=1")

        choices = {
            path: request.form.get(f"choice::{path}", "mine")
            for path in state["conflict_files"]
        }

        resolve_conflict(workspace, choices, state["remote_sha"])

        if not sync_state.mark_clean(record["id"], expected_version=state["version"]):
            return redirect(f"/apps/ark/conflicts?workspace={record['id']}&stale=1")

        auto_sync(workspace, record["id"], force=True)  # picks up anything that landed since

        return redirect("/apps/ark/")

    files = []

    for path in state["conflict_files"]:
        target = workspace / path
        mine = target.read_text(encoding="utf-8", errors="replace") if target.exists() else "[deleted locally]"
        theirs = theirs_content(workspace, path, state["remote_sha"])
        files.append({"path": path, "mine": mine, "theirs": theirs if theirs is not None else "[deleted on remote]"})

    return render_template(
        "conflicts.html",
        page_class="",
        files=files,
        version=state["version"],
        stale=request.args.get("stale") == "1",
        user=user,
        app_label=NAME,
        app_home="/apps/ark/",
        workspace_id=record["id"],
    )
