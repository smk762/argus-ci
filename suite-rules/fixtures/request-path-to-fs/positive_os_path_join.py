import os
from os.path import join, normpath

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI()
ROOT = "/srv/uploads"


# join(ROOT, "/etc/passwd") drops ROOT, and normpath/abspath keep '..': building the path with os.path
# does not make it safe.
@app.get("/read/{name}")
def read(name: str):
    return open(os.path.join(ROOT, name)).read()


@app.get("/file/{name}")
def file(name: str):
    p = os.path.abspath(os.path.join(ROOT, name))
    return FileResponse(p)


@app.delete("/rm/{name}")
def remove(name: str):
    os.remove(normpath(join(ROOT, name)))
