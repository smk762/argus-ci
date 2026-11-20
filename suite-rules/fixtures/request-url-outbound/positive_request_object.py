import requests
from fastapi import FastAPI, Request

app = FastAPI()


@app.post("/forward")
async def forward(request: Request):
    target = (await request.body()).decode()
    return requests.get(target, timeout=5).text


@app.get("/echo-host")
def echo_host(request: Request):
    return requests.get(request.url, timeout=5).text


@app.get("/callback")
def callback(request: Request):
    return requests.get(request.headers["x-callback"], timeout=5).text
