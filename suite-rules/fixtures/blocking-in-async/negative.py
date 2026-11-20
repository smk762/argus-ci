import asyncio

import httpx
import requests


async def handler(url: str) -> bytes:
    await asyncio.sleep(1)
    async with httpx.AsyncClient(timeout=5) as client:
        return (await client.get(url)).content


def sync_handler(url: str) -> bytes:  # a sync def runs in a worker thread, not on the loop
    return requests.get(url, timeout=5).content
