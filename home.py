#!/usr/bin/env python3

import os

from core.app import app

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8000,
        debug=os.environ.get("HOME_DEBUG") == "1",
    )
