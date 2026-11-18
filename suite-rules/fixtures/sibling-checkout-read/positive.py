import json
from pathlib import Path

HERE = Path(__file__).resolve()

# Each line reads another repo's checkout instead of calling its service.
SCHEMA = json.loads(Path("../argus-proof/schema/record.json").read_text())
LABELS = open("/home/smk/argus-curator/labels.txt").read()
MODELS = Path("~/argus-lens/models.toml").expanduser()
STYLES = HERE.parent / ".." / "argus-mint"
SPEC = HERE.parent / ".." / "argus_forge" / "spec" / "v1.json"
BIOS = HERE.parent.parent.parent / "argus-mint" / "bios"
TILES = HERE.parents[3] / "argus-atlas"
FEED = f"/Users/dev/argus-cull/{SCHEMA}.json"
