import requests


def fetch(url: str) -> bytes:
    return requests.get(url).content
