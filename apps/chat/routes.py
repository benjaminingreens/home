from flask import render_template, request, redirect, session

from core.auth import current_user
from core import groups as core_groups

from . import bp, NAME
from .storage import append_message, load_messages


@bp.route("/", methods=["GET", "POST"])
def home():
    user = current_user()

    if not user:
        return redirect("/login")

    user_groups = core_groups.list_user_groups(user["id"])
    group_ids = {g["id"] for g in user_groups}

    if request.method == "POST":
        action = request.form.get("action")

        if action == "switch":
            group_id = int(request.form.get("group_id", 0))

            if group_id in group_ids:
                session["chat_group_id"] = group_id

            return redirect("/apps/chat/")

        elif action == "send":
            group_id = session.get("chat_group_id")
            text = request.form.get("text", "")

            if group_id in group_ids and text.strip():
                append_message(group_id, user["username"], text)

            return redirect("/apps/chat/")

    active_group_id = session.get("chat_group_id")
    active_group = next((g for g in user_groups if g["id"] == active_group_id), None)

    if not active_group and user_groups:
        active_group = user_groups[0]
        session["chat_group_id"] = active_group["id"]

    messages = load_messages(active_group["id"]) if active_group else []

    return render_template(
        "chat_home.html",
        user=user,
        app_label=NAME,
        app_home="/apps/chat/",
        groups=user_groups,
        active_group=active_group,
        messages=messages,
    )
