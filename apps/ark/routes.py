from flask import render_template, request, redirect, abort

from core.auth import current_user
from core import workspaces as core_workspaces
from core import groups as core_groups
from core import sync_state

from . import bp, NAME
from .runner import install, run, is_git_linked, auto_sync, theirs_content, resolve_conflict


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


ARK_HELP_INTRO = (
    "ark is your personal notes and task repository. jot down notes, "
    "todos, and events as plain text - they're kept organized and synced "
    "automatically."
)

ARK_HELP = [
    ("add TYPE 'CONTENT'", "save a note/todo/evnt - e.g. add note 'buy milk'"),
    ("tidy", "sort inbox into note/todo/evnt (dry run - shows what would move)"),
    ("tidy --apply", "same, but actually applies the changes"),
]


def process(workspace, workspace_id, query):
    """Returns (records, message, is_error, help_commands) - help_commands
    is always None here, since "/help" (a universal HOME command, not an
    Ark one) is intercepted by the view before this is ever called. is_error
    marks messages that mean "that didn't work" (an Ark-reported error) so
    the template can style them differently from an ordinary result.

    Every query that reaches this function is bare - Ark's own command/
    query syntax, untouched, including mutating commands like add/tidy
    --apply/edit/archive. HOME doesn't second-guess what Ark itself
    allows; the only commands HOME intercepts itself are the universal
    "/home" and "/help", handled one level up."""

    query = query.strip()

    if not query:
        return [], "", False, None

    records, stdout, error = run(workspace, query)

    if error:
        return [], error, True, None

    if records:
        return records, "", False, None

    if stdout:
        return [], stdout, False, None

    return [], "no results", False, None


@bp.route("/", methods=["GET", "POST"])
def home():
    user, workspace, record = ark_workspace()

    if not user:
        return redirect("/login")

    if not workspace_ready(workspace):
        return redirect("/apps/ark/workspace")

    # Opportunistic pull-and-push on every visit - pulls whatever anyone
    # else has pushed since, and pushes anything committed locally (e.g.
    # by a prior save/add/tidy) that hasn't gone out yet. Best-effort: a
    # no-op if unlinked, offline, or already flagged conflicted. Throttled
    # (see core.sync_state) so a workspace only actually gets checked once
    # per few seconds, no matter how many people load this page at once.
    auto_sync(workspace, record["id"])
    conflict = sync_state.is_conflicted(record["id"])

    records = []
    query = ""
    message = ""
    is_error = False
    help_commands = None

    if request.method == "POST":
        query = request.form.get("query", "").strip()

        if query:

            # "/" is reserved for the two universal HOME commands, valid
            # from any app - everything else (including Ark's own real
            # command syntax) is bare, handled by process() below.
            if query.startswith("/"):
                command = query[1:].strip().lower()

                if command == "home":
                    return redirect("/")

                if command == "help":
                    help_commands = ARK_HELP
                else:
                    message, is_error = f"unknown command: /{command}", True

            else:
                records, message, is_error, help_commands = process(workspace, record["id"], query)

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
