from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")
cache: dict = {}


# The body of a guard runs when the check failed: the file is served exactly when the name is unknown.
@app.get("/files/{name}")
def download(name: str):
    if name not in cache:
        return FileResponse(BASE / name)
    return cache[name]
