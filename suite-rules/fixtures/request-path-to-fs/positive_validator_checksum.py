from pathlib import Path

from fastapi import FastAPI

app = FastAPI()
BASE = Path("/srv/files")


def checksum(value: str) -> int:
    return sum(value.encode())


@app.delete("/files/{name}")
def drop(name: str):
    checksum(name)
    (BASE / name).unlink()
