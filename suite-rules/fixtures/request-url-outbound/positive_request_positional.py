import httpx
import requests
import urllib.request
from fastapi import FastAPI
from urllib.request import urlopen

app = FastAPI()


# request(method, url) takes the URL second. urlopen's parameter name is url.
@app.post("/proxy")
def proxy(url: str):
    return requests.request("GET", url, timeout=5).text


@app.post("/hx")
def hx(url: str):
    return httpx.request("POST", url, timeout=5).text


@app.post("/client")
def via_client(url: str):
    client = httpx.Client()
    return client.request("GET", url, timeout=5).text


@app.post("/session")
def via_session(url: str):
    session = requests.Session()
    return session.request("GET", url, timeout=5).text


@app.post("/pool")
def via_pool(url: str):
    http = object()
    return http.request("GET", url)


@app.post("/open")
def open_url(url: str):
    return urlopen(url=url).read()


@app.post("/open-qualified")
def open_qualified(url: str):
    return urllib.request.urlopen(url=url).read()
