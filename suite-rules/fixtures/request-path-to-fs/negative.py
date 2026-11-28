from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
UPLOAD_DIR = Path("/srv/uploads")


def safe_join(root: Path, name: str) -> Path:
    p = (root / name).resolve()
    if not p.is_relative_to(root.resolve()):
        raise HTTPException(400, "bad name")
    return p


def get_settings() -> dict:
    return {"export_dir": "/srv/export"}


@app.get("/files/{name}")
def download(name: str):
    return FileResponse(safe_join(UPLOAD_DIR, name))


@app.get("/pages/{page}")
def page(page: int):
    return FileResponse(UPLOAD_DIR / f"page-{page}.html")


@app.get("/export")
def export(settings: dict = Depends(get_settings)):
    return FileResponse(Path(settings["export_dir"]) / "latest.zip")


RECORDINGS = Path("/srv/recordings")
ALLOWED = {"a.wav", "b.wav"}


@app.get("/recordings/{name}")
def recording(name: str):
    path = RECORDINGS / name
    if not path.resolve().is_relative_to(RECORDINGS.resolve()):
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/samples/{name}")
def sample(name: str):
    if name not in ALLOWED:
        raise HTTPException(404)
    return FileResponse(RECORDINGS / name)


@app.get("/ids/{name}")
def by_id(name: str):
    # An allow-list rejects before Path.name is used. `.name` alone is not a sanitizer:
    # Path("..").name is "..".
    if name not in ALLOWED:
        raise HTTPException(404)
    return FileResponse(RECORDINGS / Path(name).name)


@app.get("/exports/{name}")
def export_file(name: str):
    from argus_cortex.fs import safe_join as cortex_safe_join

    return FileResponse(cortex_safe_join(UPLOAD_DIR, name))


@app.get("/rel/{name}")
def rel(name: str):
    p = RECORDINGS / name
    p.resolve().relative_to(RECORDINGS.resolve())
    return FileResponse(p)


@app.get("/common/{name}")
def common(name: str):
    import os

    p = f"{RECORDINGS}/{name}"
    if os.path.commonpath([str(RECORDINGS), os.path.realpath(p), p]) != str(RECORDINGS):
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/chain/{name}")
def chain(name: str):
    p = RECORDINGS / name
    if not name or not p.resolve().is_relative_to(RECORDINGS.resolve()):
        return None
    return FileResponse(p)


def is_safe_name(value: str) -> bool:
    return value.isalnum()


@app.get("/pred/{name}")
def pred(name: str):
    if not is_safe_name(name):
        raise HTTPException(400)
    return FileResponse(RECORDINGS / name)


def validate_name(value: str) -> None:
    if not value.isalnum():
        raise HTTPException(400)


@app.get("/val/{name}")
def val(name: str):
    validate_name(name)
    return FileResponse(RECORDINGS / name)


@app.get("/bare/{name}")
def bare(name: str):
    if name not in ("a.wav", "b.wav"):
        return
    (RECORDINGS / name).unlink()


@app.get("/parent/{name}")
def parent(name: str):
    path = RECORDINGS / name
    if not path.is_file() or path.resolve().parent != RECORDINGS.resolve():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/manifest/{name}")
def manifest_file(name: str):
    images = {"plate.png": 1, "depth.png": 2}
    if name not in images:
        raise HTTPException(404)
    return FileResponse(RECORDINGS / name)


@app.get("/models/{name}")
def model(name: str):
    models = {"a.glb": 1}
    if name in models:
        return FileResponse(RECORDINGS / name)
    raise HTTPException(404)


@app.get("/resolved/{name}")
def resolved(name: str):
    # Resolved when assigned, then checked: the check sees the path that is served.
    p = (RECORDINGS / name).resolve()
    if not p.is_relative_to(RECORDINGS):
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/resolved-rel/{name}")
def resolved_rel(name: str):
    p = (RECORDINGS / name).resolve()
    p.relative_to(RECORDINGS)
    return FileResponse(p)


@app.get("/resolved-parent/{name}")
def resolved_parent(name: str):
    p = (RECORDINGS / name).resolve()
    if p.parent != RECORDINGS:
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/stripped/{name}")
def stripped(name: str):
    # Assigned before the guard, so the guard checks the value that is used.
    name = name.strip()
    if name not in ALLOWED:
        raise HTTPException(404)
    return FileResponse(RECORDINGS / name)
