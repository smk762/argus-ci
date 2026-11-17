import time

import requests


async def handler(url: str) -> bytes:
    time.sleep(1)
    return requests.get(url, timeout=5).content
