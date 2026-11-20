from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI()
UPLOAD_DIR = Path("/srv/uploads")


@app.get("/files/{name}")
def download(name: str):
    return FileResponse(UPLOAD_DIR / name)


@app.post("/notes")
async def save_note(title: str, body: str):
    with open(f"/srv/notes/{title}.txt", "w") as f:
        f.write(body)


@app.delete("/cache/{key}")
def drop(key: str):
    (UPLOAD_DIR / key).unlink()
