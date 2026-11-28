from flask import Flask, send_file
from werkzeug.utils import safe_join

app = Flask(__name__)
ROOT = "/srv/files"


# Werkzeug's safe_join returns None for a path outside the root; it does not raise, so calling it
# and ignoring the result checks nothing.
@app.get("/files/<name>")
def download(name: str):
    safe_join(ROOT, name)
    return send_file(f"{ROOT}/{name}")
