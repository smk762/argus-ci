import httpx
from fastapi import FastAPI

app = FastAPI()


@app.get("/ping")
async def ping(user_host: str):
    async with httpx.AsyncClient(timeout=5) as client:
        return (await client.get(user_host + "/x")).status_code
