from urllib.parse import urlencode

from flask import render_template, request, redirect, abort

from core.auth import current_user
from core import workspaces as core_workspaces
from core import groups as core_groups

from . import bp, NAME
from .runner import install, run, add, is_git_linked, sync
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


ARK_HELP = [
    ("note: <text>", "save a quick note"),
    ("todo: <text>", "save a task"),
    ("evnt: <text>", "save an event"),
    ("new <file>", "create a file"),
    ("sync", "push and pull this workspace"),
    ("home", "go to the home screen"),
]


def process(workspace, query):
    """Returns (added, records, message, help_commands, help_more_hint,
    help_extra) - the last three are None outside the help/help-more
    paths, which render.html renders via the shared _help.html partial
    instead of stuffing curated text into the generic `message` string."""

    query = query.strip()

    if not query:
        return False, [], "", None, None, None

    if query.lower() == "sync":
        _, message = sync(workspace)
        return False, [], message, None, None, None

    if query.lower() == "help":
        return False, [], "", ARK_HELP, "type 'help more' to see every ark command", None

    if query.lower() == "help more":
        _, ark_help, _ = run(workspace, "help")
        return False, [], "", ARK_HELP, None, ark_help

    if query.startswith(("note:", "todo:", "evnt:")):
        add(workspace, query)
        return True, [], "added", None, None, None

    records, stdout, error = run(workspace, query)

    if error:
        return False, [], error, None, None, None

    if records:
        return False, records, "", None, None, None

    if stdout:
        return False, [], stdout, None, None, None

    return False, [], "no results", None, None, None


@bp.route("/", methods=["GET", "POST"])
def home():
    file_path = request.args.get("file")
    workspace_id = request.args.get("workspace") if file_path else None

    user, workspace, record = ark_workspace(workspace_id)

    if not user:
        return redirect("/login")

    if not file_path and not workspace_ready(workspace):
        return redirect("/apps/ark/workspace")

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

        return render_template(
            "file.html",
            file_path=file_path,
            file_content=file_content,
            file_lines=[highlight_meta(l) for l in file_lines],
            highlight_line=highlight_line,
            user=user,
            app_label=request.args.get("app", NAME),
            app_home=request.args.get("home", "/apps/ark/"),
            workspace_id=record["id"],
        )

    records = []
    query = ""
    message = "added" if request.args.get("added") else ""
    help_commands = help_more_hint = help_extra = None

    if request.method == "POST":
        query = request.form.get("query", "").strip()

        if query:

            if query.lower() == "home":
                return redirect("/")

            if query.lower().startswith("new "):
                relpath = new_file_path(query[4:])

                if relpath:
                    create_new_file(workspace, relpath)
                    return redirect(f"/apps/ark/?file={relpath}")

                return redirect("/apps/ark/")

            added, records, message, help_commands, help_more_hint, help_extra = process(workspace, query)

            if added:
                return redirect("/apps/ark/?added=1")

    page_class = "results" if records else ""

    return render_template(
        "home.html",
        page_class=page_class,
        query=query,
        records=records,
        message=message,
        help_commands=help_commands,
        help_more_hint=help_more_hint,
        help_extra=help_extra,
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

    target = safe_file(workspace, relpath)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    qs = urlencode({"file": relpath, **({"workspace": workspace_id} if workspace_id else {})})

    return redirect(f"/apps/ark/?{qs}")
