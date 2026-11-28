import os

from argus_cortex.fs import safe_join
from fastapi import FastAPI

app = FastAPI()
ROOT = "/srv/uploads"


@app.get("/fixed/{name}")
def fixed(name: str):
    # The request value isn't in the joined path.
    return open(os.path.join(ROOT, "index.txt")).read()


@app.get("/checked/{name}")
def checked(name: str):
    # safe_join raises for a path outside ROOT; joining a constant under its result stays inside.
    return open(os.path.join(safe_join(ROOT, name), "meta.json")).read()
