import httpx
from argus_cortex.service import DependencyCheck, install_health
from fastapi import FastAPI

app = FastAPI()


def resident_fields() -> dict:
    return {"model_state": "loaded", "busy": False, "idle_s": 0.0}


async def check_store() -> DependencyCheck:
    return DependencyCheck(ok=True)


class StartingGuard:
    """A small ASGI guard in front of the app: its own 503 body for /health while the engine cannot answer.

    It registers no route; install_health below still serves /health.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "GET" and scope["path"] == "/health":
            scope = dict(scope, state={"guarded": True})
        await self.inner(scope, receive, send)


install_health(app, service="argus-widget", checks={"store": check_store}, extra=resident_fields)
app.add_middleware(StartingGuard)


@app.get("/health/gpu")
def gpu_detail():
    return {"free_mb": 0}


@app.get("/jobs/{job_id}")
def job(job_id: int):
    return {"id": job_id}


def peer_is_up(base: str) -> bool:
    # Calling a peer's /health is a client, not a route.
    return httpx.get(base.rstrip("/") + "/health", params={"checks": 0}, timeout=5).status_code == 200


def own_health(client):
    # So is a test client's or a cache's .get("/health").
    return client.get("/health").json()
