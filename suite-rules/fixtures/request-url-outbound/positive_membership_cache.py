import requests
from fastapi import FastAPI

app = FastAPI()
cache: dict[str, str] = {}


# A membership test that rejects nothing is not an allow-list.
@app.post("/preview")
def preview(url: str):
    if url in cache:
        return cache[url]
    cache[url] = requests.get(url, timeout=5).text
    return cache[url]
