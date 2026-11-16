import httpx
import requests
from fastapi import FastAPI

app = FastAPI()
BASE = "http://inference:8000"


def validate_url(url: str) -> str:
    if not url.startswith("https://api.example.com/"):
        raise ValueError("host not allowed")
    return url


@app.get("/jobs/{job_id}")
def job(job_id: str):
    return requests.get(f"{BASE}/jobs/{job_id}", timeout=5).json()


@app.post("/preview")
def preview(url: str):
    return requests.get(validate_url(url), timeout=5).text


@app.get("/models")
async def models(page: int):
    async with httpx.AsyncClient(timeout=5) as client:
        return (await client.get(BASE + "/models", params={"page": page})).json()


@app.post("/fetch")
def fetch_image(url: str):
    from argus_cortex.net import fetch

    return fetch(url, timeout=5, max_bytes=1_000_000).raise_for_status().body
