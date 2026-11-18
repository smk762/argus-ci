from pathlib import Path

from fastapi import FastAPI, Request

app = FastAPI()
UPLOAD_DIR = Path("/srv/uploads")


@app.get("/by-header")
def by_header(request: Request):
    return open(UPLOAD_DIR / request.headers["x-file"]).read()


@app.get("/by-cookie")
def by_cookie(request: Request):
    (UPLOAD_DIR / request.cookies["session"]).unlink()


@app.post("/raw")
async def raw(request: Request):
    name = (await request.body()).decode()
    with open(UPLOAD_DIR / name, "w") as f:
        f.write("x")
