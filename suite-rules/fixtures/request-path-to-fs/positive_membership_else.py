from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")
KNOWN = {"a.txt"}


# The else branch is where the value is NOT in the set.
@app.get("/files/{name}")
def download(name: str):
    if name in KNOWN:
        return {"cached": True}
    else:
        return FileResponse(BASE / name)
