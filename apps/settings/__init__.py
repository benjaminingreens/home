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

HELP_INTRO = (
    "settings covers your account, appearance, and groups - and, if "
    "you're an admin, server and user management too."
)

COMMANDS = [
    ("account", "change your username or password"),
    ("appearance", "set your accent and background colour"),
    ("groups", "create, join, and manage groups and workspaces"),
]
