# Calling the service over HTTP is the allowed pattern.
import importlib

from argus_cortex.moderation import NudeNetClient
import nudenet_client  # a different package; the name only starts the same

LABELS = "nudenet"  # a string, not an import


def sidecar():
    # A service that exists to serve the model over HTTP may import it, with a reason.
    from nudenet import NudeDetector  # nosemgrep: agpl-import -- the NudeNet sidecar itself, AGPL, served over HTTP
    return NudeDetector, NudeNetClient, importlib.import_module("json"), nudenet_client
