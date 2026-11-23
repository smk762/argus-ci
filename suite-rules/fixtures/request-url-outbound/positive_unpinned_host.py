import requests
from fastapi import FastAPI

app = FastAPI()
BASE = "https://api.internal"


# A constant prefix that does not end the authority leaves the host attacker-controlled.
@app.get("/host")
def host(target: str):
    return requests.get(f"https://{target}/api", timeout=5).text


@app.get("/fmt")
def fmt(target: str):
    return requests.get("http://{}/x".format(target), timeout=5).text


@app.get("/concat")
def concat(part: str):
    return requests.get("https://api.internal" + part, timeout=5).text


@app.get("/base")
def base(part: str):
    return requests.get(BASE + part, timeout=5).text
