import requests
from fastapi import FastAPI

app = FastAPI()


# The request value leads the f-string, so it picks the scheme and host.
@app.get("/proxy")
def proxy(user_url: str):
    return requests.get(f"{user_url}/api", timeout=5).text
