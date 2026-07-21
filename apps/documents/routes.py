from flask import render_template, request, redirect

from core.auth import current_user
from core import workspaces as core_workspaces
from core import groups as core_groups
from apps.ark.runner import auto_sync

from . import bp, NAME
from .tags import list_tags, notes_by_tags

DOCS_HELP_INTRO = (
    "documents lets you browse notes from all your ark workspaces by tag, "
    "so you don't have to remember which workspace something's filed "
    "under."
)

DOCS_HELP = [
    ("<tag>", "filter notes by tag"),
]


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

    # Documents reads straight off disk for every visible workspace, so it
    # needs the same opportunistic pull Ark's own pages trigger - otherwise
    # someone who only ever browses via Documents could be looking at
    # stale content. Same auto_sync as Ark, throttled the same way too -
    # this loop can hit several workspaces per request, so the per-
    # workspace throttle matters even more here than on a single-workspace
    # Ark page load.
    for ws in workspaces:
        auto_sync(ws["path"], ws["id"])

    selected = [t for t in request.args.get("tags", "").split(",") if t]
    all_tags = list_tags(workspaces)

    if request.method == "POST":
        raw_query = request.form.get("query", "").strip()

        # "/" is reserved for the two universal HOME commands, valid from
        # any app - everything else (here, a bare tag) is Documents' own
        # command syntax, handled below.
        if raw_query.startswith("/"):
            command = raw_query[1:].strip().lower()

            if command == "home":
                return redirect("/")

            if command == "help":
                return render_template(
                    "documents_home.html",
                    user=user,
                    app_label=NAME,
                    app_home="/apps/documents/",
                    selected=[],
                    available=[t for t in all_tags if t not in selected],
                    notes=[],
                    show_origin=len(workspaces) > 1,
                    help_commands=DOCS_HELP,
                    help_intro=DOCS_HELP_INTRO,
                    workspace_toggles=core_groups.list_all_workspaces_with_visibility(user["id"], "ark"),
                )

            return render_template(
                "documents_home.html",
                user=user,
                app_label=NAME,
                app_home="/apps/documents/",
                selected=[],
                available=[t for t in all_tags if t not in selected],
                notes=notes_by_tags(workspaces, selected),
                show_origin=len(workspaces) > 1,
                message=f"unknown command: /{command}",
                is_error=True,
                workspace_toggles=core_groups.list_all_workspaces_with_visibility(user["id"], "ark"),
            )

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
    notes = notes_by_tags(workspaces, selected) if selected else []

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

    visible_ids = {int(v) for v in request.form.getlist("visible_ids")}
    all_ids = {int(v) for v in request.form.get("all_ids", "").split(",") if v}

    for workspace_id in all_ids:
        core_groups.set_workspace_visibility(user["id"], workspace_id, workspace_id in visible_ids)

    return redirect("/apps/documents/")
