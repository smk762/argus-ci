from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")


# Wrong polarity: this raises when the path is inside the root, then still serves it when it is not.
@app.get("/files/{name}")
def download(name: str):
    p = BASE / name
    if p.resolve().is_relative_to(BASE.resolve()):
        raise HTTPException(400)
    return FileResponse(p)
