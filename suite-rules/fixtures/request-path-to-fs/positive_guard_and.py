from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")
DEBUG = False


# `and` does not dominate: when DEBUG is false the path is never checked.
@app.get("/files/{name}")
def download(name: str):
    p = BASE / name
    if DEBUG and not p.resolve().is_relative_to(BASE.resolve()):
        raise HTTPException(400)
    return FileResponse(p)
