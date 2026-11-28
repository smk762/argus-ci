from fastapi import APIRouter, FastAPI

app = FastAPI()
router = APIRouter()


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.2.3"}


@router.get("/health", include_in_schema=False)
async def router_health():
    return {"ok": True}


@app.api_route("/health", methods=["GET", "HEAD"])
async def both():
    return {"ok": True}


def build() -> FastAPI:
    inner = FastAPI()

    async def state():
        return {"model_state": "loaded"}

    inner.add_api_route("/health", state, methods=["GET"])
    inner.add_api_route(path="/health", endpoint=state)
    return inner
