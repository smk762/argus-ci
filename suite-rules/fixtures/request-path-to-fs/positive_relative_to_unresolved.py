from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")


# is_relative_to() compares parts as text: BASE / "../../etc/passwd" is "relative to" BASE.
@app.get("/files/{name}")
def download(name: str):
    p = BASE / name
    if not p.is_relative_to(BASE):
        raise HTTPException(400)
    return FileResponse(p)
