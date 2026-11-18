#!/usr/bin/env python3
"""Writes the two taint rules from one shared source definition. Run after editing; commit the output."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAFE_TYPES = ["int", "float", "bool", "UUID", "uuid.UUID", "datetime", "date"]


def _not_inside(sig: str) -> list[str]:
    out = []
    for kw in ("def", "async def"):
        out.append(f"          - pattern-not-inside: |\n              {kw} $FUNC(..., {sig}, ...):\n                ...")
    return out


def sources() -> str:
    lines = [
        "    pattern-sources:",
        "      # Parameters of a web route handler (FastAPI / Starlette / Flask style decorators),",
        "      # except injected dependencies (Depends) and parameters typed as numbers, bools, UUIDs or dates.",
        "      - patterns:",
        "          - pattern-either:",
        "              - pattern-inside: |",
        "                  @$APP.$METHOD(...)",
        "                  def $FUNC(..., $PARAM, ...):",
        "                    ...",
        "              - pattern-inside: |",
        "                  @$APP.$METHOD(...)",
        "                  async def $FUNC(..., $PARAM, ...):",
        "                    ...",
        "          - metavariable-regex:",
        "              metavariable: $METHOD",
        "              regex: ^(get|post|put|patch|delete|api_route|route|websocket)$",
    ]
    for sig in ("$PARAM = Depends(...)", "$PARAM: $T = Depends(...)", "$PARAM: Annotated[$T, Depends(...)]",
                "$PARAM: Request", "$PARAM: BackgroundTasks", "$PARAM: Response"):
        lines += _not_inside(sig)
    for t in SAFE_TYPES:
        lines += _not_inside(f"$PARAM: {t}") + _not_inside(f"$PARAM: {t} = $D")
    lines += [
        "          - focus-metavariable: $PARAM",
        "      # Request objects (Flask, Starlette)",
        "      - pattern-either:",
        "          - pattern: flask.request.$ATTR",
        "          - pattern: request.args",
        "          - pattern: request.form",
        "          - pattern: request.values",
        "          - pattern: request.files",
        "          - pattern: request.query_params",
        "          - pattern: request.path_params",
        "          - pattern: request.headers",
        "          - pattern: request.cookies",
        "          - pattern: request.url",
        "          - pattern: await request.json()",
        "          - pattern: await request.form()",
        "          - pattern: await request.body()",
        "          - pattern: request.stream()",
        "          - pattern: request.get_json(...)",
    ]
    return "\n".join(lines)


SANITIZERS = """    pattern-sanitizers:
      - pattern: int(...)
      - pattern: float(...)
      - pattern: os.path.basename(...)
      - pattern: Path(...).name
      - pattern: PurePath(...).name
      # A validation call, an allow-list membership test or a containment check clears the value
      # it checks from then on, whether or not it is used as the condition of an if.
      - by-side-effect: true
        patterns:
          - pattern: $F(..., $X, ...)
          - metavariable-regex:
              metavariable: $F
              regex: (?i).*(safe|secure|sanitiz|validat|allow|within|under_root|check|require|match|or_404|resolve_under).*
          - focus-metavariable: $X
      - by-side-effect: true
        patterns:
          - pattern-either:
              - pattern: $X in $C
              - pattern: $X not in $C
          - focus-metavariable: $X
      # Resolving a path is how code checks containment (is_relative_to, parent ==, commonpath).
      - by-side-effect: true
        patterns:
          - pattern: $X.resolve(...)
          - focus-metavariable: $X
      - by-side-effect: true
        patterns:
          - pattern: os.path.commonpath([..., $X, ...])
          - focus-metavariable: $X
      # A guard that rejects early: `if <... X.resolve() ... or a validator of X ...>: raise`.
      # (semgrep doesn't carry side effects out of a short-circuit `or` chain, so say it directly.)
      - patterns:
          - pattern-inside: |
              if <... $X.resolve() ...>:
                  raise ...
              ...
          - pattern: $X"""

PATH_SINKS = """    pattern-sinks:
      # Where the path is used, not where it is built: code often builds a path and checks it
      # before touching the filesystem.
      - patterns:
          - pattern-either:
              - pattern: open($P, ...)
              - pattern: io.open($P, ...)
              - pattern: open(Path($P), ...)
              - pattern: os.open($P, ...)
              - pattern: os.remove($P)
              - pattern: os.unlink($P)
              - pattern: shutil.$FN($P, ...)
              - pattern: shutil.$FN($A, $P, ...)
              - pattern: FileResponse($P, ...)
              - pattern: send_file($P, ...)
              - pattern: send_from_directory($D, $P, ...)
              - pattern: Path($P).$M(...)
              - patterns:
                  - pattern: $P.$M(...)
                  - metavariable-regex:
                      metavariable: $M
                      regex: ^(open|read_text|read_bytes|write_text|write_bytes|unlink|rmdir|mkdir|rename|replace|touch|symlink_to|iterdir|glob|rglob)$
          - focus-metavariable: $P"""

URL_SINKS = """    pattern-sinks:
      # Only when the request value is (or starts) the URL: a fixed base URL with a request value
      # appended later can't move the host, so f-strings and concatenations are not sinks.
      - patterns:
          - pattern-either:
              - pattern: requests.$M($U, ...)
              - pattern: requests.$M(url=$U, ...)
              - pattern: httpx.$M($U, ...)
              - pattern: httpx.$M(url=$U, ...)
              - pattern: urllib.request.urlopen($U, ...)
              - pattern: urlopen($U, ...)
              - patterns:
                  - pattern-either:
                      - pattern: $C.$M($U, ...)
                      - pattern: $C.$M(url=$U, ...)
                  - metavariable-regex:
                      metavariable: $C
                      regex: (?i).*(client|session|http).*
                  - metavariable-regex:
                      metavariable: $M
                      regex: ^(get|post|put|patch|delete|head|options|request|stream)$
          - pattern-not: $X.$M(f"...", ...)
          - pattern-not: $X.$M("..." + $Y, ...)
          - pattern-not: $X.$M($A + $B, ...)
          - pattern-not: $X.$M("...".format(...), ...)
          - focus-metavariable: $U"""

EXCLUDE = """    paths:
      exclude:
        - "tests/"
        - "test_*.py"
        - "*_test.py"
        - "conftest.py\""""

HEADER = "# Generated by _generate.py from one shared source definition; edit that file, not this one.\n"


def rule(rid: str, cls: str, message: str, sinks: str) -> str:
    # message and class go in as JSON strings, which are valid YAML double-quoted scalars: a newline,
    # `: `, `#` or a leading `[`/`&` in them can't break the document or add keys.
    return (f"{HEADER}rules:\n  - id: {rid}\n    mode: taint\n"
            "    options:\n      taint_assume_safe_functions: true\n      taint_assume_safe_indexes: true\n"
            f"    languages: [python]\n    severity: ERROR\n"
            f"    message: {json.dumps(message)}\n    metadata:\n      class: {json.dumps(cls)}\n      catalogue: argus-ci/suite-rules\n"
            f"{EXCLUDE}\n{sources()}\n{SANITIZERS}\n{sinks}\n")


def main() -> None:
    (HERE / "request-path-to-fs.yml").write_text(rule(
        "request-path-to-fs", "path_traversal",
        "Request input reaches a filesystem path. Use argus_cortex.fs.safe_join(root, value), or safe_name for a single id, which returns the resolved path under root or raises PathRefused.",
        PATH_SINKS))
    (HERE / "request-url-outbound.yml").write_text(rule(
        "request-url-outbound", "ssrf",
        "Request input becomes the URL of an outbound call (SSRF). Fetch it with argus_cortex.net.fetch / afetch, which checks every resolved address, pins the connection and re-checks redirects; pass allow_hosts for internal services.",
        URL_SINKS))
    print("wrote request-path-to-fs.yml, request-url-outbound.yml")


if __name__ == "__main__":
    main()
