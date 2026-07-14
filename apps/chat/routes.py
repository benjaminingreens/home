from flask import render_template, request, redirect

from core.auth import current_user
from apps.ark.routes import resolve_active_workspace

from . import bp, NAME
from .storage import append_message, load_messages


@bp.route("/", methods=["GET", "POST"])
def home():
    """Chat follows the same "current group" every other app uses (the
    group behind users.active_workspace_id, switched via the topbar's
    group menu) rather than its own independent session-based selector -
    one place to switch group, not two."""

    user = current_user()

    if not user:
        return redirect("/login")

    active = resolve_active_workspace(user)
    group_id = active["group_id"]

    if request.method == "POST":
        text = request.form.get("text", "")

        if text.strip():
            append_message(group_id, user["username"], text)

        return redirect("/apps/chat/")

    return render_template(
        "chat_home.html",
        page_class="chat",
        user=user,
        app_label=NAME,
        app_home="/apps/chat/",
        group_name=active["group_name"],
        messages=load_messages(group_id),
    )
