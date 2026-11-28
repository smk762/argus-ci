import httpx
from fastapi import FastAPI

app = FastAPI()


# All keywords: client.request(method=..., url=...). A positional method pattern doesn't bind it.
@app.post("/client")
async def via_client(url: str):
    async with httpx.AsyncClient() as client:
        return (await client.request(method="GET", url=url, timeout=5)).text
