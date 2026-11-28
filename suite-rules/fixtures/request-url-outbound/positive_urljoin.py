from urllib.parse import urljoin

import httpx
from fastapi import FastAPI

app = FastAPI()
BASE = "http://catalogue:8000/"


# urljoin(BASE, "http://169.254.169.254/") returns the second URL: the base pins nothing.
@app.get("/proxy")
def proxy(path: str):
    return httpx.get(urljoin(BASE, path), timeout=5).text
