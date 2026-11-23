from pathlib import Path

from fastapi import FastAPI

app = FastAPI()
BASE = Path("/srv/files")
ALLOWED = {"a.txt"}
DEBUG = True


# Inside the body an `or` operand does not dominate: DEBUG alone enters it.
@app.get("/files/{name}")
def download(name: str):
    if name in ALLOWED or DEBUG:
        return open(BASE / name).read()
    return "no"
