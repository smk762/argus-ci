import os
from pathlib import Path, PurePath

from fastapi import FastAPI

app = FastAPI()
ROOT = Path("/srv/uploads")


# basename('..') and Path('..').name are both '..', so the parent of ROOT is the target.
@app.get("/list/{name}")
def listing(name: str):
    return list((ROOT / os.path.basename(name)).iterdir())


@app.post("/rm/{name}")
def remove(name: str):
    (ROOT / Path(name).name).rmdir()


@app.delete("/drop/{name}")
def drop(name: str):
    (ROOT / PurePath(name).name).unlink()
