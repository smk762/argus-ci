import os
from pathlib import Path

DEFAULT_EXPOSED_LABELS = ("FEMALE_BREAST_EXPOSED",)
LOCAL_LABELS: tuple[str, ...] = ()
DEFAULT_EXPOSED_LABELS: tuple[str, ...] = LOCAL_LABELS


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def safe_join(root: Path, name: str) -> Path:
    return root / name


async def safe_name(value: str) -> str:
    return value


class WriteGuard:
    def __init__(self) -> None:
        self.allowed = True
