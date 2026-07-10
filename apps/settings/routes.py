import sqlite3

from flask import render_template, request, redirect

from core.auth import current_user
from core.users import verify_password, update_password, create, list_users
from core.db import connect
from core import groups as core_groups

from . import bp, NAME

VALID_VISIBILITY = ("private", "server", "federated")


@bp.route("/", methods=["GET", "POST"])
def account():
    user = current_user()

    if not user:
        return redirect("/login")

    message = ""
    error = ""

    if request.method == "POST" and request.form.get("action") == "change_password":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not verify_password(current_password, user["password"]):
            error = "current password is wrong"
        elif len(new_password) < 8:
            error = "new password must be at least 8 characters"
        elif new_password != confirm_password:
            error = "new passwords do not match"
        else:
            update_password(user["id"], new_password)
            message = "password changed"
            user = current_user()

    return render_template(
        "settings_account.html",
        user=user,
        app_label=NAME,
        app_home="/apps/settings/",
        section="account",
        message=message,
        error=error,
    )


@bp.route("/visibility", methods=["GET", "POST"])
def visibility():
    user = current_user()

    if not user:
        return redirect("/login")

    message = ""
    error = ""

    if request.method == "POST":
        v = request.form.get("visibility", "server")

        if v in VALID_VISIBILITY:
            with connect() as con:
                con.execute("UPDATE users SET visibility=? WHERE id=?", (v, user["id"]))
            message = "visibility updated"
            user = current_user()

    return render_template(
        "settings_visibility.html",
        user=user,
        app_label=NAME,
        app_home="/apps/settings/",
        section="visibility",
        message=message,
        error=error,
    )


@bp.route("/groups", methods=["GET", "POST"])
def groups_page():
    user = current_user()

    if not user:
        return redirect("/login")

    message = ""
    error = ""

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "create_group":
            name = request.form.get("group_name", "").strip()

            if name:
                core_groups.create_group(name, user["id"])
                message = f"created group {name}"
            else:
                error = "group name is required"

        elif action == "invite_member":
            try:
                group_id = int(request.form.get("group_id", 0))
                invitee_id = int(request.form.get("invitee_id", 0))
                core_groups.invite_member(group_id, user["id"], invitee_id)
                message = "invite sent"
            except (PermissionError, ValueError) as e:
                error = str(e)

        elif action == "respond_invite":
            try:
                group_id = int(request.form.get("group_id", 0))
                accept = request.form.get("accept") == "1"
                core_groups.respond_to_invite(group_id, user["id"], accept)
                message = "joined group" if accept else "invite declined"
            except ValueError as e:
                error = str(e)

    groups_view = []
    for g in core_groups.list_user_groups(user["id"]):
        groups_view.append({
            "id": g["id"],
            "name": g["name"],
            "is_personal": g["is_personal"],
            "members": core_groups.list_group_members(g["id"]),
            "invitable": [] if g["is_personal"] else core_groups.list_invitable_users(g["id"]),
        })

    return render_template(
        "settings_groups.html",
        user=user,
        app_label=NAME,
        app_home="/apps/settings/",
        section="groups",
        message=message,
        error=error,
        groups=groups_view,
        pending_invites=core_groups.list_pending_invites(user["id"]),
    )


@bp.route("/servers", methods=["GET", "POST"])
def servers():
    user = current_user()

    if not user:
        return redirect("/login")

    message = ""
    error = ""

    if request.method == "POST":
        host = request.form.get("host", "").strip()

        if host:
            try:
                with connect() as con:
                    con.execute("INSERT INTO federated_servers (host) VALUES (?)", (host,))
                message = "server recorded (federation is not yet functional)"
            except sqlite3.IntegrityError:
                error = "that server is already added"
        else:
            error = "host is required"

    with connect() as con:
        federated_servers = con.execute(
            "SELECT * FROM federated_servers ORDER BY host"
        ).fetchall()

    return render_template(
        "settings_servers.html",
        user=user,
        app_label=NAME,
        app_home="/apps/settings/",
        section="servers",
        message=message,
        error=error,
        federated_servers=federated_servers,
    )


@bp.route("/accounts", methods=["GET", "POST"])
def accounts():
    user = current_user()

    if not user:
        return redirect("/login")

    if not user["is_admin"]:
        return redirect("/apps/settings/")

    message = ""
    error = ""

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "create_user":
            new_username = request.form.get("new_username", "").strip().lower()
            new_password = request.form.get("new_user_password", "").strip()

            if not new_username or not new_password:
                error = "username and password are required"
            elif len(new_password) < 8:
                error = "password must be at least 8 characters"
            else:
                create(new_username, new_password, must_change_password=True)
                message = f"created account for {new_username}"

        elif action == "reset_user_password":
            target_id = request.form.get("user_id", "")
            new_password = request.form.get("reset_password", "").strip()

            if not new_password or len(new_password) < 8:
                error = "password must be at least 8 characters"
            elif target_id:
                update_password(int(target_id), new_password, must_change_password=True)
                message = "password reset"

    return render_template(
        "settings_accounts.html",
        user=user,
        app_label=NAME,
        app_home="/apps/settings/",
        section="accounts",
        message=message,
        error=error,
        all_users=list_users(),
    )
