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


@app.post("/upload")
def upload(filename: str, data: bytes):
    (UPLOAD_DIR / Path(filename).name).write_bytes(data)


@app.get("/exports/{name}")
def export_file(name: str):
    from argus_cortex.fs import safe_join as cortex_safe_join

    return FileResponse(cortex_safe_join(UPLOAD_DIR, name))
