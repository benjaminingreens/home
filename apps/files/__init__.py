from flask import Blueprint

NAME = "Files"
DESCRIPTION = "Browse, create, move, and delete files"

bp = Blueprint(
    "files",
    __name__,
    url_prefix="/apps/files",
    template_folder="templates",
)

from . import routes

HELP_INTRO = routes.FILES_HELP_INTRO
COMMANDS = routes.FILES_HELP
