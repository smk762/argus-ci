import contextlib
import json
import logging

logger = logging.getLogger(__name__)


def load(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        logger.warning("config %s unreadable: %s", path, exc)
    return {}


def free_cache(torch) -> None:
    # Best effort: an allocator that can't free now will on the next call.
    with contextlib.suppress(Exception):
        torch.cuda.empty_cache()
