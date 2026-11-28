from urllib.parse import urljoin

import httpx
from fastapi import FastAPI

app = FastAPI()
BASE = "http://catalogue:8000/"


@app.get("/health")
def health(verbose: bool = False):
    # Only constants are joined.
    return httpx.get(urljoin(BASE, "health"), timeout=5).json()
