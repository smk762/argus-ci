import os
from pathlib import Path

from argus_cortex.fs import safe_join
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from werkzeug.utils import safe_join as wz_safe_join

app = FastAPI()
BASE = Path("/srv/files")
ROOT = "/srv/files"


# Resolved when assigned, so is_relative_to() sees the real location.
@app.get("/resolved/{name}")
def resolved(name: str):
    p = (BASE / name).resolve()
    if not p.is_relative_to(BASE.resolve()):
        raise HTTPException(400)
    return FileResponse(p)


@app.get("/resolved-check/{name}")
def resolved_check(name: str):
    p = BASE / name
    if not p.resolve().is_relative_to(BASE.resolve()):
        raise HTTPException(400)
    return FileResponse(p)


@app.get("/realpath/{name}")
def via_realpath(name: str):
    p = f"{ROOT}/{name}"
    if os.path.commonpath([ROOT, os.path.realpath(p)]) != ROOT:
        raise HTTPException(400)
    return FileResponse(p)


@app.get("/abspath/{name}")
def via_abspath(name: str):
    p = f"{ROOT}/{name}"
    if ROOT != os.path.commonpath([ROOT, os.path.abspath(p)]):
        raise HTTPException(400)
    return FileResponse(p)


@app.get("/resolved-common/{name}")
def resolved_common(name: str):
    p = BASE / name
    if os.path.commonpath([BASE, p.resolve()]) != BASE:
        raise HTTPException(400)
    return FileResponse(p)


# argus_cortex.fs.safe_join raises PathRefused, so the name is clean after it.
@app.get("/cortex/{name}")
def via_cortex(name: str):
    safe_join(BASE, name)
    return FileResponse(BASE / name)


@app.get("/werkzeug/{name}")
def via_werkzeug(name: str):
    if wz_safe_join(ROOT, name) is None:
        raise HTTPException(404)
    return FileResponse(f"{ROOT}/{name}")
