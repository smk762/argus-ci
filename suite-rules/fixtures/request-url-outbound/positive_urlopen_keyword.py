import urllib.request
from urllib.request import urlopen

from fastapi import FastAPI

app = FastAPI()


@app.get("/a")
def via_import(url: str):
    return urlopen(url=url, timeout=5).read()


@app.get("/b")
def via_module(url: str):
    return urllib.request.urlopen(url=url, timeout=5).read()
