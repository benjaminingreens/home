from .config import *
from .db import init as init_db

def init():

    DATA.mkdir(exist_ok=True)

    WORKSPACES.mkdir(exist_ok=True)

    init_db()
