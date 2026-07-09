from flask import render_template, request, redirect

from core.auth import current_user
from core.workspaces import app as app_workspace
from apps.ark.routes import safe_file

from . import bp, NAME
from .tags import list_tags, notes_by_tags


def documents_workspace():
    user = current_user()

    if not user:
        return None, None

    return user, app_workspace(user["username"], "ark")


@bp.route("/", methods=["GET", "POST"])
def home():
    user, workspace = documents_workspace()

    if not user:
        return redirect("/login")

    selected = [t for t in request.args.get("tags", "").split(",") if t]
    all_tags = list_tags(workspace)

    if request.method == "POST":
        raw_query = request.form.get("query", "").strip()

        if raw_query.lower().startswith("new "):
            relpath = raw_query[4:].strip()

            if relpath:
                if not relpath.split("/", 1)[0] in ("note", "todo", "evnt"):
                    relpath = f"note/{relpath}"

                target = safe_file(workspace, relpath)
                target.parent.mkdir(parents=True, exist_ok=True)

                if not target.exists():
                    target.write_text("", encoding="utf-8")

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
    notes = notes_by_tags(workspace, selected)

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
    )
