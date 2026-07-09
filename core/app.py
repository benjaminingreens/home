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
from .users import ensure_admin

ROOT = Path(__file__).resolve().parent.parent

init()
ensure_admin()

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


EXEMPT_PATHS = ("/login", "/logout", "/register")


@app.before_request
def enforce_password_change():

    if request.path.startswith("/static/"):
        return

    if request.path in EXEMPT_PATHS or request.path.startswith("/apps/settings"):
        return

    user = current_user()

    if user and user["must_change_password"]:
        return redirect("/apps/settings/")


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

            app_id = resolve_launch(query, APPS)

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
