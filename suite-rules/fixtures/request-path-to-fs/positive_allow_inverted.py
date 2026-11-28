from pathlib import Path

from fastapi import FastAPI, HTTPException

app = FastAPI()
BASE = Path("/srv/files")
ALLOWED = {"a.txt"}


# Wrong polarity: `not (name not in ALLOWED)` is `name in ALLOWED`, and the raise does not confine it.
@app.get("/files/{name}")
def download(name: str):
    if not (name not in ALLOWED):
        raise HTTPException(404)
    return open(BASE / name).read()
