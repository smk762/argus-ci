from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")
ALLOWED = {"a.txt", "b.txt"}


# The guard checked the old value. After the assignment `name` is one it never saw.
@app.get("/files/{name}/{other}")
def download(name: str, other: str):
    if name not in ALLOWED:
        raise HTTPException(404)
    name = other
    return FileResponse(BASE / name)
