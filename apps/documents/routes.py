from flask import render_template, request, redirect

from core.auth import current_user
from core import workspaces as core_workspaces
from core import groups as core_groups
from apps.ark.routes import new_file_path, create_new_file, resolve_active_workspace

from . import bp, NAME
from .tags import list_tags, notes_by_tags


def visible_workspaces(user):
    records = core_groups.list_visible_workspaces(user["id"], "ark")

    return [
        {
            "id": r["id"],
            "path": core_workspaces.path(r["group_slug"], "ark", r["name"]),
            "label": f"{r['group_name']} / {r['name']}",
        }
        for r in records
    ]


@bp.route("/", methods=["GET", "POST"])
def home():
    user = current_user()

    if not user:
        return redirect("/login")

    workspaces = visible_workspaces(user)
    selected = [t for t in request.args.get("tags", "").split(",") if t]
    all_tags = list_tags(workspaces)

    if request.method == "POST":
        raw_query = request.form.get("query", "").strip()

        if raw_query.lower() == "help":
            message = (
                "home commands:\n"
                "  <tag>        filter notes by tag\n"
                "  new <file>   create a file\n"
                "  help         this message\n\n"
                "use the workspaces menu (tap the app name above) to choose\n"
                "which workspaces' notes show up here."
            )

            return render_template(
                "documents_home.html",
                user=user,
                app_label=NAME,
                app_id="documents",
                app_home="/apps/documents/",
                selected=[],
                available=[t for t in all_tags if t not in selected],
                notes=notes_by_tags(workspaces, selected),
                show_origin=len(workspaces) > 1,
                message=message,
                workspace_toggles=core_groups.list_all_workspaces_with_visibility(user["id"], "ark"),
            )

        if raw_query.lower().startswith("new "):
            relpath = new_file_path(raw_query[4:])

            if relpath:
                active = resolve_active_workspace(user)
                target = core_workspaces.path(active["group_slug"], "ark", active["name"])
                create_new_file(target, relpath)

                return redirect(
                    f"/apps/ark/?file={relpath}&app=Documents&home=/apps/documents/"
                )

            return redirect("/apps/documents/")

        query = raw_query.lstrip("#").lower()

        if query:
            match = (
                next((t for t in all_tags if t.lower() == query), None)
                or next((t for t in all_tags if t.lower().startswith(query)), None)
            )

            if match and match not in selected:
                selected = selected + [match]

        return redirect(f"/apps/documents/?tags={','.join(selected)}")

    available = [t for t in all_tags if t not in selected]
    notes = notes_by_tags(workspaces, selected)

    selected_view = [
        {
            "tag": t,
            "remove_href": "/apps/documents/?tags="
                + ",".join(x for x in selected if x != t),
        }
        for t in selected
    ]

    return render_template(
        "documents_home.html",
        user=user,
        app_label=NAME,
        app_id="documents",
        app_home="/apps/documents/",
        selected=selected_view,
        available=available,
        notes=notes,
        show_origin=len(workspaces) > 1,
        workspace_toggles=core_groups.list_all_workspaces_with_visibility(user["id"], "ark"),
    )


@bp.post("/visibility")
def toggle_visibility():
    user = current_user()

    if not user:
        return redirect("/login")

    workspace_id = int(request.form.get("workspace_id", 0))
    visible = request.form.get("visible") == "1"

    core_groups.set_workspace_visibility(user["id"], workspace_id, visible)

    return redirect("/apps/documents/")
