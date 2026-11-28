from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI()
ROOT = Path("/srv/uploads")


# `.name` of '..' is '..' on every pathlib class, not only Path and PurePath.
@app.get("/posix/{name}")
def posix(name: str):
    return FileResponse(ROOT / PurePosixPath(name).name)


@app.get("/windows/{name}")
def windows(name: str):
    return FileResponse(ROOT / PureWindowsPath(name).name)
