import httpx
import requests
from fastapi import FastAPI

app = FastAPI()
client = httpx.Client(timeout=5)
PEER = "inference:8000"


# A template in second place is only safe when its prefix pins the host. These do not.
@app.get("/a/{host}")
def a(host: str):
    return client.request("GET", f"https://{host}/status").json()


# The hole in the authority is the sink, wherever the constant ones are.
@app.get("/b/{host}")
def b(host: str):
    return requests.get(f"https://api.{host}/users/{PEER}", timeout=5).json()


@app.get("/c/{host}")
def c(host: str):
    return requests.get("https://{}/users/{}".format(host, PEER), timeout=5).json()


@app.get("/d/{port}")
def d(port: str):
    return requests.get(f"http://{PEER}:{port}/users", timeout=5).json()


# A template as the body does not make the URL before it safe.
@app.post("/e")
def e(url: str, note: str):
    return requests.post(url, f"note: {note}", timeout=5).text
