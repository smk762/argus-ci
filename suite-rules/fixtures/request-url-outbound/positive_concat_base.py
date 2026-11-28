import requests
from fastapi import FastAPI

app = FastAPI()
BASE = "https://api.internal"


# No slash after the host: user="@evil.com" sends the request to evil.com.
@app.get("/ping")
def ping(user: str):
    return requests.get(BASE + user, timeout=5).text
