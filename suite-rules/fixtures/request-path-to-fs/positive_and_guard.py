from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")


# `and` does not dominate: when debug is false the path is used unchecked.
@app.get("/files/{name}")
def download(name: str, debug: bool = False):
    p = BASE / name
    if debug and not p.resolve().is_relative_to(BASE.resolve()):
        raise HTTPException(400)
    return FileResponse(p)
