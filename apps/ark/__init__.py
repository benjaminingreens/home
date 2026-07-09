from flask import Blueprint

NAME = "Ark"
DESCRIPTION = "Personal knowledge repository"

bp = Blueprint(
    "ark",
    __name__,
    url_prefix="/apps/ark",
    template_folder="templates",
    static_folder="static",
)

from . import routes
from .runner import install
