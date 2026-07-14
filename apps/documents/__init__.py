from flask import Blueprint

NAME = "Documents"
DESCRIPTION = "Browse Ark notes by tag"

bp = Blueprint(
    "documents",
    __name__,
    url_prefix="/apps/documents",
    template_folder="templates",
)

from . import routes

HELP_INTRO = routes.DOCS_HELP_INTRO
COMMANDS = routes.DOCS_HELP
