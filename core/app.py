from .auth import current_user
from pathlib import Path
from .apps import load_apps, resolve_launch

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    abort,
)

from .storage import init
from .auth import login
from .users import create

ROOT = Path(__file__).resolve().parent.parent

init()

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
)

APPS = load_apps(app)

from apps.ark import routes as ark_routes

app.secret_key = "development"

@app.get("/apps")
def apps():

    user = current_user()

    if not user:
        return redirect("/login")

    return render_template(
        "apps.html",
        title="Apps",
        user=user,
        apps=APPS,
    )


@app.route("/", methods=["GET", "POST"])
def index():

    user = current_user()

    if not user:
        return redirect("/login")

    records = []
    query = ""

    if request.method == "POST":
        query = request.form.get("query", "").strip()

        if query:

            app_id = resolve_launch(query, APPS)

            if app_id:
                return redirect(f"/apps/{app_id}/")

            _, workspace = ark_routes.ark_workspace()

            added, records = ark_routes.process(workspace, query)

            if added:
                return redirect("/")

    page_class = "results" if records else ""

    return render_template(
        "index.html",
        title="Home",
        page_class=page_class,
        query=query,
        records=records,
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


@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        create(
            request.form["username"],
            request.form["password"],
        )

        return redirect("/login")

    return render_template(
        "register.html",
        title="Register",
    )
