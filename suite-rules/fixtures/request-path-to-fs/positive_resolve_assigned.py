from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI()
BASE = Path("/srv/files")


# Assigning the resolved path checks nothing either: ../../etc/passwd resolves and is served.
@app.get("/files/{name}")
def download(name: str):
    p = (BASE / name).resolve()
    return FileResponse(p)
