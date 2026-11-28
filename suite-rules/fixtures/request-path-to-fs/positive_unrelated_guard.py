from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")


# A guard that mentions X.resolve() but tests existence, not containment.
@app.get("/files/{name}")
def download(name: str):
    p = BASE / name
    if not p.resolve().exists():
        raise HTTPException(404)
    return FileResponse(p)
