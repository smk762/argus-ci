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


# A rejecting guard: `if <cond>: raise / abort / return`, with the code after it in scope.
REJECTS = ("raise ...", "abort(...)", "flask.abort(...)", "return ...")  # `return ...` also matches a bare return


def _guard(conds: list[str], comment: str, where: str = "") -> str:
    """A sanitizer for $X after `if <one of conds>: <reject>`. `<... c ...>` lets the test sit in an and/or chain
    (semgrep doesn't carry side effects out of a short-circuit chain)."""
    out = [f"      # {comment}", "      - patterns:", "          - pattern-either:"]
    for c in conds:
        for rej in REJECTS:
            out.append(f"              - pattern-inside: |\n                  if <... {c} ...>:\n"
                       f"                      ...\n                      {rej}\n                  ...")
    return "\n".join(out) + where + "\n          - pattern: $X"


# Callee names, anchored on the function's own name (the last dotted part).
# Validators that raise on a bad value clear it by side effect; predicates only count inside a rejecting guard.
RAISING_VALIDATOR = r"^(.*\.)?(validate_\w+|ensure_(safe|valid|allowed|within|under)\w*|require_(safe|valid|allowed|within|under)\w*|safe_join|safe_name|safe_path|resolve_under\w*|\w+_or_404)$"
PREDICATE = r"^(.*\.)?(is_\w*(safe|valid|allowed|permitted|within|under_root)\w*|\w+_is_(safe|valid|allowed)|allowed_\w+|\w+_(allowed|permitted))$"

SANITIZERS = "\n".join([
    """    pattern-sanitizers:
      - pattern: int(...)
      - pattern: float(...)
      - pattern: os.path.basename(...)
      - pattern: Path(...).name
      - pattern: PurePath(...).name
      # A validator that raises on a bad value clears it from then on.
      - by-side-effect: true
        patterns:
          - pattern: $F(..., $X, ...)
          - metavariable-regex:
              metavariable: $F
              regex: """ + RAISING_VALIDATOR + """
          - focus-metavariable: $X
      # relative_to raises ValueError when the resolved path is outside the root.
      - by-side-effect: true
        patterns:
          - pattern: $X.resolve(...).relative_to(...)
          - focus-metavariable: $X""",
    _guard(["not $X.resolve(...).is_relative_to(...)", "not $X.is_relative_to(...)",
            "$X.resolve(...).parent != $B", "$B != $X.resolve(...).parent",
            "os.path.commonpath([..., $X, ...]) != $B", "$B != os.path.commonpath([..., $X, ...])"],
           "A containment guard: `if not X.resolve().is_relative_to(root): raise`, or the parent / commonpath form."),
    _guard(["not $F(..., $X, ...)"], "A predicate validator as a rejecting guard: `if not is_safe(X): abort(400)`.",
           "\n          - metavariable-regex:\n              metavariable: $F\n              regex: " + PREDICATE),
    _guard(["$X not in $C"], "An allow-list guard: `if X not in ALLOWED: raise`. A membership test that rejects nothing\n"
           "      # (`if url in cache: ...`, `if name not in seen: seen.add(name)`) is not one."),
    """      # The body of `if X in ALLOWED:`, but not when that if has an else (semgrep's pattern-inside would cover it).
      - patterns:
          - pattern-inside: |
              if <... $X in $C ...>:
                  ...
          - pattern-not-inside: |
              if <... $X in $C ...>:
                  ...
              else:
                  ...
          - pattern: $X""",
])

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


def _url_calls(arg: str) -> str:
    """`- pattern-either:` over the outbound calls, with `arg` as the URL argument (positional or url=)."""
    out = ["          - pattern-either:"]
    for call in ("requests.$M", "httpx.$M", "urllib.request.urlopen", "urlopen"):
        out.append(f"              - pattern: {call}({arg}, ...)")
        if call.endswith("$M"):
            out.append(f"              - pattern: {call}(url={arg}, ...)")
    out += [
        "              - patterns:",
        "                  - pattern-either:",
        f"                      - pattern: $C.$M({arg}, ...)",
        f"                      - pattern: $C.$M(url={arg}, ...)",
        "                  - metavariable-regex:",
        "                      metavariable: $C",
        "                      regex: (?i).*(client|session|http).*",
        "                  - metavariable-regex:",
        "                      metavariable: $M",
        "                      regex: ^(get|post|put|patch|delete|head|options|request|stream)$",
    ]
    return "\n".join(out)


TEMPLATES = ('f"..."', "$A + $B", "$S.format(...)")

URL_SINKS = "\n".join([
    """    pattern-sinks:
      # Only what decides the scheme and host is a sink: the URL itself, or the leading part of a template.
      # A request value after a constant prefix (f"https://api/{x}", BASE + x) can't move the host.
      - patterns:""",
    _url_calls("$U"),
    *(f"          - pattern-not: $F({kw}{t}, ...)" for t in TEMPLATES for kw in ("", "url=")),
    """          - focus-metavariable: $U
      # A template: the sink is its leading part (f"{U}/api", U + "/x").
      - patterns:""",
    _url_calls("$ARG"),
    """          - metavariable-pattern:
              metavariable: $ARG
              pattern-either:
                - pattern: f"{$U}..."
                - pattern: $U + $R
          - focus-metavariable: $U
      # "{}/x".format(u): the placeholder leads, so every format argument is a sink.
      - patterns:""",
    _url_calls("$S.format(..., $U, ...)"),
    """          - metavariable-regex:
              metavariable: $S
              regex: ^[rRbBuU]*["']\\{
          - focus-metavariable: $U""",
])

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
