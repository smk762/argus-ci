from pathlib import Path

from fastapi import FastAPI, HTTPException

app = FastAPI()
BASE = Path("/srv/files")
ALLOWED = {"a.txt"}
DEBUG = False


# `and` does not dominate an allow-list reject.
@app.get("/files/{name}")
def download(name: str):
    if DEBUG and name not in ALLOWED:
        raise HTTPException(404)
    return open(BASE / name).read()
