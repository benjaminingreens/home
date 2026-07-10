from pathlib import Path
from urllib.parse import urlencode

from flask import render_template, request, redirect, abort

from core.auth import current_user
from core.workspaces import app as app_workspace
from core import workspaces as core_workspaces

from . import bp, NAME
from .runner import install, run, add, is_git_linked, sync


def ark_workspace():
    user = current_user()
    if not user:
        return None, None

    workspace = app_workspace(user["username"], "ark")

    return user, workspace


def workspace_ready(workspace):
    return (workspace / ".ark").exists()


def safe_file(workspace, relpath):
    relpath = relpath.strip() or "note/inbox.txt"
    target = (workspace / relpath).resolve()

    if workspace.resolve() not in target.parents and target != workspace.resolve():
        abort(403)

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
    user, workspace = ark_workspace()

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
    )


@bp.route("/workspace", methods=["GET", "POST"])
def workspace_setup():
    user, workspace = ark_workspace()

    if not user:
        return redirect("/login")

    username = user["username"]
    error = ""
    message = ""

    if request.method == "POST":
        action = request.form.get("action")

        if action == "new":
            install(workspace)
            return redirect("/apps/ark/")

        elif action == "start_link":
            core_workspaces.start_link(username, "ark")

        elif action == "finish_link":
            try:
                core_workspaces.finish_link(username, "ark")
                return redirect("/apps/ark/")
            except ValueError as e:
                error = str(e)

        elif action == "enable_git":
            try:
                core_workspaces.enable_git(username, "ark")
                message = "local sync enabled"
            except ValueError as e:
                error = str(e)

    ready = workspace_ready(workspace)
    linked = is_git_linked(workspace)
    bare_started = core_workspaces.has_bare_repo(username, "ark")

    if not ready:
        state = "linking" if bare_started else "choose"
    elif not linked:
        state = "upgrade"
    else:
        state = "linked"

    remote = (
        core_workspaces.remote_url(username, "ark")
        if (bare_started or linked)
        else None
    )

    return render_template(
        "workspace.html",
        user=user,
        app_label=NAME,
        app_home="/apps/ark/",
        state=state,
        remote=remote,
        error=error,
        message=message,
    )


@bp.post("/sync")
def sync_route():
    user, workspace = ark_workspace()

    if not user:
        return redirect("/login")

    ok, sync_message = sync(workspace)

    qs = urlencode({"sync_msg": sync_message, "sync_ok": int(ok)})

    return redirect(f"/apps/ark/?{qs}")


@bp.post("/save")
def save():
    user, workspace = ark_workspace()

    if not user:
        return redirect("/login")

    relpath = request.form.get("path", "note/inbox.txt")
    content = request.form.get("content", "")

    target = safe_file(workspace, relpath)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return redirect(f"/apps/ark/?file={relpath}")
