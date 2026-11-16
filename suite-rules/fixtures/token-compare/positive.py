import os

from fastapi import Header, HTTPException

API_TOKEN = os.environ.get("API_TOKEN", "")


def require_token(x_api_token: str = Header("")) -> None:
    if x_api_token != API_TOKEN:
        raise HTTPException(401)


def verify(body: bytes, signature: str, secret: bytes) -> bool:
    import hashlib
    import hmac

    return signature == hmac.new(secret, body, hashlib.sha256).hexdigest()


def admin_ok(authorization: str, token: str) -> bool:
    return authorization == f"Bearer {token}"
