import os
from pathlib import Path

from fastapi import FastAPI

app = FastAPI()
ROOT = Path("/data/items")


@app.get("/items/{item_id}")
def get_item(item_id: str) -> dict:
    for path in ROOT.glob("*.json"):
        if path.stem == item_id:
            return {"path": str(path)}
    return {}


@app.post("/rebuild")
async def rebuild() -> dict:
    return {"n": len(os.listdir(ROOT))}
