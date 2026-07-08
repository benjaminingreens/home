from .config import *
from .db import init as init_db

def init():

    DATA.mkdir(parents=True, exist_ok=True)
    WORKSPACES.mkdir(parents=True, exist_ok=True)

    init_db()
