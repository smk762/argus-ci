import httpx
import requests
from fastapi import FastAPI

app = FastAPI()


@app.post("/preview")
def preview(url: str):
    return requests.get(url, timeout=5).text


@app.post("/webhook-test")
async def webhook_test(target: str):
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.post(target, json={"ping": True})
    return r.status_code
