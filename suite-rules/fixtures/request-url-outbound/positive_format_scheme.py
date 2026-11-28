import httpx
from fastapi import FastAPI

app = FastAPI()


@app.get("/status")
def status(host: str):
    return httpx.get("http://{}/x".format(host), timeout=5).text
