import requests
from fastapi import FastAPI

app = FastAPI()


# The prefix is only the scheme, so the request value is the host.
@app.get("/proxy")
def proxy(host: str):
    return requests.get(f"https://{host}/api", timeout=5).text
