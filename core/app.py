from .auth import current_user
from pathlib import Path
from .apps import load_apps

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


@app.get("/")
def index():

    user = current_user()

    if not user:

        return redirect("/login")

    return render_template(
        "index.html",
        title="Home",
        user=user,
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
