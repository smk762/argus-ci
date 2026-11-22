from pathlib import Path

from fastapi import FastAPI

app = FastAPI()
BASE = Path("/srv/files")
seen: set[str] = set()


@app.get("/files/{name}")
def download(name: str):
    if name not in seen:
        seen.add(name)
    return open(BASE / name).read()
