import httpx
from fastapi import FastAPI

app = FastAPI()
client = httpx.Client(timeout=5)


# stream(method, url) takes the URL second, like request().
@app.get("/proxy")
def proxy(url: str):
    with client.stream("GET", url) as r:
        return r.read()


@app.get("/proxy2")
def proxy2(url: str):
    with httpx.stream("GET", url, timeout=5) as r:
        return r.read()
