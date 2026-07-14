import secrets
import warnings

from .auth import current_user
from pathlib import Path
from .apps import load_apps, resolve_launch
from .config import SECRET_KEY

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    abort,
)

from .storage import init
from .auth import login, logout
from .users import has_any_users, create_first_admin
from . import groups as core_groups
from .colors import theme_colors, tag_color, colorize_meta

ROOT = Path(__file__).resolve().parent.parent

init()

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
)

APPS = load_apps(app)

if SECRET_KEY:
    app.secret_key = SECRET_KEY
else:
    warnings.warn(
        "HOME_SECRET_KEY is not set; using a random key for this process only. "
        "Sessions will not persist across restarts. Set HOME_SECRET_KEY in production."
    )
    app.secret_key = secrets.token_hex(32)

app.jinja_env.filters["tag_color"] = tag_color
app.jinja_env.filters["colorize_meta"] = colorize_meta


EXEMPT_PATHS = ("/login", "/logout", "/register", "/setup")


@app.before_request
def enforce_setup():

    if request.path.startswith("/static/"):
        return

    if request.path == "/setup":
        return

    if not has_any_users():
        return redirect("/setup")


@app.before_request
def enforce_password_change():

    if request.path.startswith("/static/"):
        return

    if request.path in EXEMPT_PATHS or request.path.startswith("/apps/settings"):
        return

    user = current_user()

    if user and user["must_change_password"]:
        return redirect("/apps/settings/")


@app.context_processor
def inject_topbar_context():
    user = current_user()

    if not user:
        return {}

    # Deferred import: apps.ark.routes imports from core.groups/core.workspaces,
    # and this module is imported (via load_apps) before those blueprints
    # exist, so importing it at module load time here would be premature.
    from apps.ark.routes import resolve_active_workspace

    active = resolve_active_workspace(user)
    bg_color = user["background_color"]

    theme = theme_colors(bg_color)

    return {
        "current_user_ctx": user,
        "current_group": {"id": active["group_id"], "name": active["group_name"]},
        "user_groups": core_groups.list_user_groups(user["id"]),
        "nav_apps": APPS,
        "bg_color": bg_color,
        "fg_color": theme["fg"],
        "fg_muted_color": theme["fg_muted"],
        "fg_faint_color": theme["fg_faint"],
        "border_color": theme["border"],
    }


@app.post("/group")
def switch_group():
    user = current_user()

    if not user:
        return redirect("/login")

    group_id = int(request.form.get("group_id", 0))

    if not core_groups.require_active_member(user["id"], group_id):
        abort(403)

    workspace = core_groups.get_or_create_group_default_workspace(group_id, "ark", user["id"])
    core_groups.set_active_workspace(user["id"], workspace["id"])

    return redirect(request.referrer or "/")


@app.get("/apps")
def apps():

    user = current_user()

    if not user:
        return redirect("/login")

    return render_template(
        "apps.html",
        title="Apps",
        user=user,
        app_label="apps",
        app_home="/apps",
        apps=APPS,
    )


@app.route("/", methods=["GET", "POST"])
def index():

    user = current_user()

    if not user:
        return redirect("/login")

    query = ""
    message = ""

    if request.method == "POST":
        query = request.form.get("query", "").strip()

        if query:

            # There's no "app" to defer to on the launcher itself, so bare
            # input is already system-level here - a leading "/" is
            # accepted too, just for consistency with every other screen.
            lookup = query.lstrip("/")

            if lookup.lower() == "help":
                message = "type an app name to open it, or start typing to filter the list below."
            else:
                app_id = resolve_launch(lookup, APPS)

                if app_id:
                    return redirect(f"/apps/{app_id}/")

                message = "no such app"

    return render_template(
        "index.html",
        title="Home",
        page_class="",
        query=query,
        records=[],
        message=message,
        user=user,
        app_label="home",
        placeholder="type an app name, or 'help'...",
        apps=APPS,
    )


@app.route("/login", methods=["GET","POST"])
def login_page():

    if request.method == "POST":

        if login(
            request.form["username"],
            request.form["password"],
        ):
            return redirect("/")

    return render_template(
        "login.html",
        title="Login",
    )


@app.get("/logout")
def logout_page():

    logout()

    return redirect("/login")


@app.get("/register")
def register():
    # Public self-registration is disabled. Accounts are created by an
    # admin from within Settings.
    return redirect("/login")


@app.route("/setup", methods=["GET", "POST"])
def setup_page():
    # One-time, first-run only: creates the initial admin account. Once
    # any account exists, this permanently redirects to /login instead.
    if has_any_users():
        return redirect("/login")

    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not password:
            error = "username and password are required"
        elif len(password) < 8:
            error = "password must be at least 8 characters"
        elif password != confirm:
            error = "passwords do not match"
        elif not create_first_admin(username, password):
            error = "setup was already completed"
        else:
            login(username, password)
            return redirect("/")

    return render_template(
        "setup.html",
        title="Set up HOME",
        error=error,
    )
