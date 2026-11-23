import os
from pathlib import Path

from fastapi import FastAPI

app = FastAPI()
ROOT = Path("/srv/uploads")


# basename('..') is '..', so this lists the parent of ROOT.
@app.get("/list/{name}")
def listing(name: str):
    return list((ROOT / os.path.basename(name)).iterdir())


@app.delete("/dir/{name}")
def drop(name: str):
    (ROOT / Path(name).name).rmdir()
