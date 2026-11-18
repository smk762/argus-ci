from pathlib import Path

import httpx

HERE = Path(__file__).resolve()

# This repo's own files, service names, and siblings reached over HTTP.
ROOT = HERE.parents[2]
PKG = HERE.parents[1] / "argus_mask"
CATALOGUE = HERE.parent.parent / "src" / "argus_mask" / "editor" / "asset_catalogue.json"
DATA = Path("../data/inputs.json")
SERVICE = "argus-proof"
APP_TITLE = "argus-curator"
URL = "http://argus-proof:8080/schema"
HOME = Path("/home/app/.cache")


def schema() -> dict:
    return httpx.get(URL, timeout=5).json()
