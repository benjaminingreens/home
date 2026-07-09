from flask import Blueprint

NAME = "Settings"
DESCRIPTION = "Account and admin settings"

bp = Blueprint(
    "settings",
    __name__,
    url_prefix="/apps/settings",
    template_folder="templates",
)

from . import routes
