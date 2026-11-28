import httpx
import requests
from fastapi import FastAPI

app = FastAPI()


@app.post("/relay")
def relay(url: str):
    return requests.request("GET", url, timeout=5).text


@app.post("/hx")
def hx(url: str):
    return httpx.request("POST", url, timeout=5).text


@app.post("/client")
async def via_client(url: str):
    async with httpx.AsyncClient(timeout=5) as client:
        return (await client.request("PUT", url)).text
