import re
from pathlib import Path

from fastapi import FastAPI

app = FastAPI()
BASE = Path("/srv/files")


# A call named like a check, with its result ignored, checks nothing.
@app.get("/files/{name}")
def download(name: str):
    re.match(r".*", name)
    return open(BASE / name).read()
