import shlex
from urllib.parse import urlsplit, urlencode, parse_qsl

from flask import render_template, request, redirect, abort

from core.auth import current_user
from core import workspaces as core_workspaces
from core import groups as core_groups
from core import sync_state

from . import bp, NAME
from .runner import install, run, is_git_linked, auto_sync, theirs_content, resolve_conflict, known_commands


def redirect_after_switch():
    """Where a workspace-switching endpoint sends you back to: the page
    you switched from, same as before, but with any workspace= query
    param stripped out first. Files' own links always carry an explicit
    workspace= (see apps.files.routes.entry_links, deliberate - so a
    shared link always means a specific workspace regardless of whoever
    clicks it) - left untouched, switching from a Files page would just
    bounce back to that same stale workspace= and look like the switch
    silently did nothing."""

    referrer = request.referrer

    if not referrer:
        return redirect("/apps/ark/")

    parts = urlsplit(referrer)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != "workspace"])
    target = parts.path + (f"?{query}" if query else "")

    return redirect(target)


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


def git_root_for(record):
    """git's scope is the whole workspace root, one level above the app's
    own data folder (ark_workspace()'s `workspace`) that ark's own
    commands run against - see core.workspaces.hoist_git_to_root for why."""

    return core_workspaces.root(record["group_slug"], "ark", record["name"])


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


def multiview_workspaces(user, primary_record):
    """Every workspace a multiview query should run against: the active
    ("primary") one, plus whatever's pinned via the topbar's
    checkbox-style switcher (see core.groups.list_multiview_selection) -
    filtered to workspaces the user is still an active member of, in case
    a pin outlived their membership. Order matters: primary first, so
    process_multiview's first-error/first-stdout fallback favors it."""

    ids = [primary_record["id"]]

    for workspace_id in core_groups.list_multiview_selection(user["id"]):
        if workspace_id not in ids:
            ids.append(workspace_id)

    records = []

    for workspace_id in ids:
        record = core_groups.get_workspace(workspace_id)

        if record and core_groups.require_active_member(user["id"], record["group_id"]):
            records.append(record)

    return records


def process_multiview(workspace_records, query):
    """Same contract as process(), but runs a read query across several
    workspaces at once and merges the results - each tagged with its
    origin group/workspace (see _terminal.html) so a mixed result list
    stays legible, the same way the old Documents app labeled entries by
    origin workspace.

    Mutating commands (add/tidy/edit/...) are refused here rather than
    fanned out to every selected workspace: HOME deliberately doesn't
    parse Ark's own command semantics beyond knowing a command *name*
    (see known_commands()), so it has no reliable way to know which of
    them are safe to run more than once, in more than one place, from a
    single button press. Narrowing to one workspace (unchecking the
    others) always gets you back to the normal single-workspace path."""

    query = query.strip()

    if not query:
        return [], "", False, None

    tokens = shlex.split(query)

    if tokens and tokens[0].lower() in known_commands():
        return (
            [],
            "commands need a single active workspace - unpin the extra ones first",
            True,
            None,
        )

    records = []
    stdout = ""
    error = ""

    for record in workspace_records:
        workspace = core_workspaces.path(record["group_slug"], "ark", record["name"])
        found, out, err = run(workspace, query)

        if err:
            error = error or err
            continue

        for r in found:
            r["origin_group"] = record["group_name"]
            r["origin_workspace"] = record["name"]
            r["origin_workspace_id"] = record["id"]

        records.extend(found)
        stdout = stdout or out

    if records:
        return records, "", False, None

    if error:
        return [], error, True, None

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
    auto_sync(git_root_for(record), record["id"])
    conflict = sync_state.is_conflicted(record["id"])

    multiview_records = multiview_workspaces(user, record)
    is_multiview = len(multiview_records) > 1

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
            # command syntax) is bare, handled by process()/process_multiview()
            # below.
            if query.startswith("/"):
                command = query[1:].strip().lower()

                if command == "home":
                    return redirect("/")

                if command == "help":
                    help_commands = ARK_HELP
                else:
                    message, is_error = f"unknown command: /{command}", True

            elif is_multiview:
                records, message, is_error, help_commands = process_multiview(multiview_records, query)
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
        git_linked=is_git_linked(git_root_for(record)),
        active_workspace_id=record["id"],
    )


@bp.post("/workspaces")
def switch_workspace():
    """The topbar's single-select switcher posts here, from any app's
    page (see inject_topbar_context) - creating workspaces lives in
    Settings, next to the group it belongs to; this endpoint only
    switches which existing one is active, then returns to wherever the
    switch was made from."""

    user = current_user()

    if not user:
        return redirect("/login")

    try:
        core_groups.set_active_workspace(user["id"], int(request.form.get("workspace_id", 0)))
    except (ValueError, PermissionError):
        pass

    return redirect_after_switch()


@bp.get("/workspaces/new")
def new_default_workspace():
    """The switcher's fallback for a group with no workspace yet (a
    brand-new shared group has none until someone explicitly creates
    one) - lazily creates and switches to its 'default' workspace, same
    convention as a personal group's own default (see
    resolve_active_workspace). A plain link rather than a form post so it
    works standalone inside the switcher's accordion, which - for a
    multiview app - is itself one big form (see set_multiview); nested
    <form> elements aren't valid HTML."""

    user = current_user()

    if not user:
        return redirect("/login")

    try:
        record = core_groups.get_or_create_group_default_workspace(
            int(request.args.get("group_id", 0)), "ark", user["id"]
        )
        core_groups.set_active_workspace(user["id"], record["id"])
    except (ValueError, PermissionError):
        pass

    return redirect_after_switch()


@bp.post("/multiview")
def set_multiview():
    """The topbar switcher's checkbox accordion (multiview apps only -
    see core.apps.load_apps' MULTIVIEW flag) posts here once, when the
    menu closes, with every currently-checked workspace_id - not one
    request per checkbox, so ticking several boxes doesn't reload the
    page in between (see closeMenus() in _topbar.html).

    The active workspace is always implicitly part of the set; if its
    box was unchecked, another checked one is promoted to active instead
    (there must always be exactly one active workspace - every other app
    depends on it) rather than leaving multiview with no primary at all.
    Order follows submission order (roughly group-then-workspace DOM
    order), so the promoted one is whichever checked box comes first."""

    user = current_user()

    if not user:
        return redirect("/login")

    checked_ids = []

    for raw in request.form.getlist("workspace_id"):
        try:
            workspace_id = int(raw)
        except ValueError:
            continue

        if workspace_id in checked_ids:
            continue

        record = core_groups.get_workspace(workspace_id)

        if record and core_groups.require_active_member(user["id"], record["group_id"]):
            checked_ids.append(workspace_id)

    active_id = user["active_workspace_id"]

    if checked_ids and active_id not in checked_ids:
        active_id = checked_ids[0]
        core_groups.set_active_workspace(user["id"], active_id)

    core_groups.set_multiview_extras(user["id"], [wid for wid in checked_ids if wid != active_id])

    return redirect_after_switch()


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
    linked = is_git_linked(git_root_for(record))
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
        active_workspace_id=record["id"],
    )


@bp.route("/conflicts", methods=["GET", "POST"])
def conflicts():
    workspace_id = request.values.get("workspace")
    user, _, record = ark_workspace(workspace_id)

    if not user:
        return redirect("/login")

    # Conflict state is git's - resolving/reading conflicted files works
    # against the git root, not ark's own narrower data folder (see
    # git_root_for), since conflicted paths (e.g. "ark/note/foo.md") are
    # relative to the root now.
    workspace = git_root_for(record)

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
