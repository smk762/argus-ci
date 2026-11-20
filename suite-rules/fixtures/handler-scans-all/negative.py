import json
from pathlib import Path

from fastapi import FastAPI

app = FastAPI()
ROOT = Path("/data/items")


def rebuild_index() -> None:  # not a handler: run on write or from a job
    index = {p.stem: str(p) for p in ROOT.glob("*.json")}
    (ROOT / "index.json").write_text(json.dumps(index))


@app.get("/items/{item_id}")
def get_item(item_id: str) -> dict:
    return {"path": str(ROOT / f"{item_id}.json")}
