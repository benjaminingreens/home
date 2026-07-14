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

HELP_INTRO = (
    "chat is a simple group message log, shared with everyone in your "
    "current group. messages can't be edited or deleted once sent."
)

COMMANDS = [
    ("enter", "send your message"),
    ("shift+enter", "insert a newline"),
]
