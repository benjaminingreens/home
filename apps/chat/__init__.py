from flask import Blueprint

NAME = "Chat"
DESCRIPTION = "Group chat"

bp = Blueprint(
    "chat",
    __name__,
    url_prefix="/apps/chat",
    template_folder="templates",
)

from . import routes
