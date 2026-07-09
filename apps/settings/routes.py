from flask import render_template, request, redirect

from core.auth import current_user
from core.users import verify_password, update_password, create, list_users

from . import bp, NAME


@bp.route("/", methods=["GET", "POST"])
def home():
    user = current_user()

    if not user:
        return redirect("/login")

    message = ""
    error = ""

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "change_password":
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

        elif action == "create_user" and user["is_admin"]:
            new_username = request.form.get("new_username", "").strip().lower()
            new_password = request.form.get("new_user_password", "").strip()

            if not new_username or not new_password:
                error = "username and password are required"
            elif len(new_password) < 8:
                error = "password must be at least 8 characters"
            else:
                create(new_username, new_password, must_change_password=True)
                message = f"created account for {new_username}"

        elif action == "reset_user_password" and user["is_admin"]:
            target_id = request.form.get("user_id", "")
            new_password = request.form.get("reset_password", "").strip()

            if not new_password or len(new_password) < 8:
                error = "password must be at least 8 characters"
            elif target_id:
                update_password(int(target_id), new_password, must_change_password=True)
                message = "password reset"

    all_users = list_users() if user["is_admin"] else []

    return render_template(
        "settings_home.html",
        user=user,
        app_label=NAME,
        app_home="/apps/settings/",
        message=message,
        error=error,
        all_users=all_users,
    )
