import hmac
import os

API_TOKEN = os.environ.get("API_TOKEN", "")


def require_token(x_api_token: str) -> bool:
    return hmac.compare_digest(x_api_token.encode(), API_TOKEN.encode())


def under_budget(total_tokens: int, max_tokens: int) -> bool:
    return total_tokens == max_tokens


def is_unset(token: str | None) -> bool:
    return token == "" or token is None


def same_kind(token_type: str, expected_type: str) -> bool:
    return token_type == expected_type


def intact(data: bytes, expected_sha256: str) -> bool:
    import hashlib

    return hashlib.sha256(data).hexdigest() == expected_sha256


def same_file(a, b) -> bool:
    return a.digest() == b.digest()


def find_key(session, ApiKey, hashed_key: str):
    return session.query(ApiKey).filter(ApiKey.hashed_key == hashed_key).first()


class Library:
    def fresh(self, signature: tuple) -> bool:
        return self._scanned is not None and self._scanned[0] == signature
