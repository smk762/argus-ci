import httpx
from fastapi import FastAPI

app = FastAPI()


@app.get("/status")
def status(target: str):
    return httpx.get("{}/x".format(target), timeout=5).text
