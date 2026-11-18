from argus_cortex.fs import safe_join, safe_name
from argus_cortex.moderation.nudenet import DEFAULT_EXPOSED_LABELS
from argus_cortex.server import WriteGuard, env_flag

LABELS = DEFAULT_EXPOSED_LABELS
GUARD = WriteGuard


def resolve_upload(root, name):
    return safe_join(root, safe_name(name))


def env_flag_or(name: str, default: bool) -> bool:
    return env_flag(name) or default


class UploadGuard(WriteGuard):
    pass
