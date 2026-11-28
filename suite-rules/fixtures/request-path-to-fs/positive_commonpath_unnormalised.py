import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
BASE = "/srv/files"


# commonpath() doesn't collapse "..": commonpath(["/srv/files", "/srv/files/../../etc/passwd"]) is "/srv/files".
@app.get("/files/{name}")
def download(name: str):
    p = f"{BASE}/{name}"
    if os.path.commonpath([BASE, p]) != BASE:
        raise HTTPException(400)
    return FileResponse(p)
