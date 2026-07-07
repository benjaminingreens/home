#!/usr/bin/env python3

from http.server import HTTPServer, BaseHTTPRequestHandler

from core.storage import init

init()

class Home(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header("Content-Type", "text/html")

        self.end_headers()

        self.wfile.write(b"""
<h1>Home</h1>

<p>Installation successful.</p>
""")

HTTPServer(("0.0.0.0",8000),Home).serve_forever()
