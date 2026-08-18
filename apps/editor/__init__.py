from flask import Blueprint

NAME = "Editor"
DESCRIPTION = "Generic file viewer/editor"

# Never shows up in the launcher or app-switcher - you only ever arrive
# here via a file=/workspace= link from whichever app you were in.
HIDDEN = True

bp = Blueprint(
    "editor",
    __name__,
    url_prefix="/apps/editor",
    template_folder="templates",
)

from . import routes
