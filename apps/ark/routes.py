import sqlite3
from urllib.parse import urlencode

from flask import render_template, request, redirect, abort

from core.auth import current_user
from core import workspaces as core_workspaces
from core import groups as core_groups

from . import bp, NAME
from .runner import install, run, add, is_git_linked, sync


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


def ark_workspace():
    user = current_user()

    if not user:
        return None, None, None

    record = resolve_active_workspace(user)
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


def process(workspace, query):
    query = query.strip()

    if not query:
        return False, [], ""

    if query.startswith(("note:", "todo:", "evnt:")):
        add(workspace, query)
        return True, [], "added"

    records, stdout, error = run(workspace, query)

    if error:
        return False, [], error

    if records:
        return False, records, ""

    if stdout:
        return False, [], stdout

    return False, [], "no results"


@bp.route("/", methods=["GET", "POST"])
def home():
    user, workspace, record = ark_workspace()

    if not user:
        return redirect("/login")

    if not workspace_ready(workspace):
        return redirect("/apps/ark/workspace")

    file_path = request.args.get("file")

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
            file_lines=file_lines,
            highlight_line=highlight_line,
            user=user,
            app_label=request.args.get("app", NAME),
            app_home=request.args.get("home", "/apps/ark/"),
        )

    records = []
    query = ""

    if request.args.get("sync_msg") is not None:
        message = request.args.get("sync_msg", "")
    elif request.args.get("added"):
        message = "added"
    else:
        message = ""

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

            added, records, message = process(workspace, query)

            if added:
                return redirect("/apps/ark/?added=1")

    page_class = "results" if records else ""

    return render_template(
        "home.html",
        page_class=page_class,
        query=query,
        records=records,
        message=message,
        user=user,
        app_label=NAME,
        app_home="/apps/ark/",
        apps=[],
        git_linked=is_git_linked(workspace),
        workspace_label=f"{record['group_name']} / {record['name']}",
    )


@bp.route("/workspaces", methods=["GET", "POST"])
def workspaces_list():
    user = current_user()

    if not user:
        return redirect("/login")

    error = ""

    if request.method == "POST":
        action = request.form.get("action")

        try:
            if action == "switch":
                core_groups.set_active_workspace(user["id"], int(request.form.get("workspace_id", 0)))
                return redirect("/apps/ark/")

            elif action == "create":
                group_id = int(request.form.get("group_id", 0))
                name = request.form.get("name", "").strip()

                record = core_groups.create_workspace_record(group_id, "ark", name, user["id"])
                core_groups.set_active_workspace(user["id"], record["id"])

                return redirect("/apps/ark/workspace")

        except (ValueError, PermissionError) as e:
            error = str(e)
        except sqlite3.IntegrityError:
            error = "a workspace with that name already exists in this group"

    return render_template(
        "workspaces.html",
        user=user,
        app_label=NAME,
        app_home="/apps/ark/",
        groups=core_groups.list_user_groups(user["id"]),
        workspaces=core_groups.list_all_workspaces_with_visibility(user["id"], "ark"),
        error=error,
    )


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
    )


@bp.post("/sync")
def sync_route():
    user, workspace, record = ark_workspace()

    if not user:
        return redirect("/login")

    ok, sync_message = sync(workspace)

    qs = urlencode({"sync_msg": sync_message, "sync_ok": int(ok)})

    return redirect(f"/apps/ark/?{qs}")


@bp.post("/save")
def save():
    user, workspace, record = ark_workspace()

    if not user:
        return redirect("/login")

    relpath = request.form.get("path", "note/inbox.txt")
    content = request.form.get("content", "")

    target = safe_file(workspace, relpath)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return redirect(f"/apps/ark/?file={relpath}")
