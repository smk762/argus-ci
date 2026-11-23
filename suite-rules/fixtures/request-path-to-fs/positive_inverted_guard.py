from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")
ALLOWED = {"a.txt", "b.txt"}


# The polarity is backwards: the reject runs when the name IS allowed.
@app.get("/files/{name}")
def download(name: str):
    if not (name not in ALLOWED):
        raise HTTPException(400)
    return FileResponse(BASE / name)
