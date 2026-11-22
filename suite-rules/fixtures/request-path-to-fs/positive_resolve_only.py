from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")


# Resolving a path doesn't confine it: ../../etc/passwd resolves fine.
@app.get("/files/{name}")
def download(name: str):
    p = BASE / name
    p.resolve()
    return FileResponse(p)
