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


# The check dominates the reject when it is the whole test or a direct `or` operand: surviving
# means that operand was false. An `and` operand does not (`if flag and bad(x): raise` falls
# through while x is bad), and a further `not` flips the test. `<... c ...>` matches both.
_GUARD_FORMS = (
    "if {c}:",
    "if {c} or ...:",
    "if ... or {c}:",
    "if ... or {c} or ...:",
)


def _guard(conds: list[str], comment: str, where: str = "") -> str:
    """A sanitizer for $X after a rejecting guard that one of `conds` dominates.

    Only the code after the `if` is cleared. Its body runs when the check failed
    (`if X not in cache: return FileResponse(root / X)`), so X is still unchecked there; the else
    branch is left out with it. And only until X is assigned again: `X = other` after the guard is
    a value the guard never saw.
    """
    out = [f"      # {comment}", "      - patterns:", "          - pattern-either:"]
    after = []
    for c in conds:
        for form in _GUARD_FORMS:
            test = form.format(c=c)
            for rej in REJECTS:
                out.append(f"              - pattern-inside: |\n                  {test}\n"
                           f"                      ...\n                      {rej}\n                  ...")
            after.append(f"          - pattern-not-inside: |\n              {test}\n                  ...")
            after.append(f"          - pattern-not-inside: |\n              {test}\n                  ...\n"
                         "              ...\n              $X = $V\n              ...")
    return "\n".join(out + after) + where + "\n          - pattern: $X"


def _commonpath(x: str) -> list[str]:
    """`commonpath([..., x, ...])` differing from the root, either way round."""
    return [f"os.path.commonpath([..., {x}, ...]) != $B", f"$B != os.path.commonpath([..., {x}, ...])"]


# `$X = <path>.resolve()` earlier in the block: $X holds a resolved path, so a containment check on it counts.
_RESOLVED = "\n          - pattern-inside: |\n              $X = $R.resolve(...)\n              ..."

# os.path functions that collapse `..`, so commonpath() over their result means containment.
_NORMALISED = "\n          - metavariable-regex:\n              metavariable: $NORM\n              regex: ^(realpath|abspath|normpath)$"


def _in_allowlist_body() -> str:
    """The body of `if X in ALLOWED` when that check dominates and the if has no else.

    Inside the body an `and` operand is true; an `or` operand is not (`if X in ALLOWED or flag`),
    and a negated test is the complement. The else branch is the complement too.
    """
    forms = (
        "if $X in $C:",
        "if $X in $C and ...:",
        "if ... and $X in $C:",
        "if ... and $X in $C and ...:",
    )
    lines = [
        "      # The body of `if X in ALLOWED`, when that check dominates and the if has no else.",
        "      - patterns:",
        "          - pattern-either:",
    ]
    for form in forms:
        lines.append(f"              - pattern-inside: |\n                  {form}\n                      ...")
    for form in forms:
        lines.append("          - pattern-not-inside: |\n"
                     f"              {form}\n                  ...\n              else:\n                  ...")
    lines.append("          - pattern: $X")
    return "\n".join(lines)


# Callee names, anchored on the function's own name (the last dotted part).
# Validators that raise on a bad value clear it by side effect; predicates only count inside a rejecting guard.
# `safe_join` is argus_cortex.fs's, which raises; Werkzeug's and Flask's return None instead (WERKZEUG_SAFE_JOIN).
RAISING_VALIDATOR = r"^(.*\.)?(validate_\w+|ensure_(safe|valid|allowed|within|under)\w*|require_(safe|valid|allowed|within|under)\w*|safe_join|safe_name|safe_path|resolve_under\w*|\w+_or_404)$"
PREDICATE = r"^(.*\.)?(is_\w*(safe|valid|allowed|permitted|within|under_root)\w*|\w+_is_(safe|valid|allowed)|allowed_\w+|\w+_(allowed|permitted))$"

# Werkzeug's safe_join (and Flask's re-export) returns None for a path that leaves the root; it never raises.
WERKZEUG_SAFE_JOIN = ("werkzeug.utils.safe_join", "werkzeug.security.safe_join", "flask.safe_join",
                      "flask.helpers.safe_join")

SANITIZERS = "\n".join([
    """    pattern-sanitizers:
      - pattern: int(...)
      - pattern: float(...)
      # basename('..') and Path('..').name are '..', so neither confines a path.
      # A validator that raises on a bad value clears it from then on.
      - by-side-effect: true
        patterns:
          - pattern: $F(..., $X, ...)
          - metavariable-regex:
              metavariable: $F
              regex: """ + RAISING_VALIDATOR + "\n" + "\n".join(
    f"          - pattern-not: {c}(...)" for c in WERKZEUG_SAFE_JOIN) + """
          - focus-metavariable: $X
      # relative_to raises ValueError when the resolved path is outside the root.
      - by-side-effect: true
        patterns:
          - pattern: $X.resolve(...).relative_to(...)
          - focus-metavariable: $X
      # The same on a path that was resolved when it was assigned: `p = (root / X).resolve()`, `p.relative_to(root)`.
      - by-side-effect: true
        patterns:
          - pattern-inside: |
              $X = $R.resolve(...)
              ...
          - pattern: $X.relative_to(...)
          - focus-metavariable: $X""",
    _guard(["not $X.resolve(...).is_relative_to(...)", "$X.resolve(...).parent != $B", "$B != $X.resolve(...).parent",
            *_commonpath("$X.resolve(...)"), *_commonpath("str($X.resolve(...))")],
           "A containment guard: `if not X.resolve().is_relative_to(root): raise`, or the parent / commonpath form.\n"
           "      # Neither is_relative_to() nor commonpath() collapses `..`, so the path they see must be resolved:\n"
           "      # `if not X.is_relative_to(root)` on an unresolved X passes root / '../../etc/passwd'."),
    _guard(["not $X.is_relative_to(...)", "$X.parent != $B", "$B != $X.parent", *_commonpath("$X"), *_commonpath("str($X)")],
           "The same guard on a path resolved when it was assigned: `p = (root / X).resolve()`, then\n"
           "      # `if not p.is_relative_to(root): raise`. resolve() alone confines nothing, so p stays tainted until here.",
           _RESOLVED),
    _guard(_commonpath("os.path.$NORM($X)"),
           "commonpath() over the normalised path: `if os.path.commonpath([root, os.path.realpath(X)]) != root`.",
           _NORMALISED),
    _guard([f"{c}(..., $X, ...) is None" for c in WERKZEUG_SAFE_JOIN],
           "Werkzeug's safe_join returns None for a path outside the root: `if safe_join(root, X) is None: abort(404)`."),
    _guard(["not $F(..., $X, ...)"], "A predicate validator as a rejecting guard: `if not is_safe(X): abort(400)`.",
           "\n          - metavariable-regex:\n              metavariable: $F\n              regex: " + PREDICATE),
    _guard(["$X not in $C"], "An allow-list guard: `if X not in ALLOWED: raise`. A membership test that rejects nothing\n"
           "      # (`if url in cache: ...`, `if name not in seen: seen.add(name)`) is not one."),
    _in_allowlist_body(),
])

# taint_assume_safe_functions would swallow these calls. They pass '..' through (resolve() follows
# it out of the root), so the argument's taint has to reach the result. by-side-effect is false so
# the function itself is not tainted for a later call with a safe argument.
PROPAGATORS = r"""    pattern-propagators:
      - by-side-effect: false
        patterns:
          - pattern: $F($X)
          - focus-metavariable: $F
          - metavariable-regex:
              metavariable: $F
              regex: ^(.*\.)?basename$
        from: $X
        to: $F
      - by-side-effect: false
        patterns:
          - pattern: $F($X).name
          - focus-metavariable: $F
          - metavariable-regex:
              metavariable: $F
              regex: ^(.*\.)?(Pure)?(Posix|Windows)?Path$
        from: $X
        to: $F
      - by-side-effect: false
        patterns:
          - pattern: $F(...)
          - metavariable-pattern:
              metavariable: $F
              pattern: $X.resolve
          - focus-metavariable: $F
        from: $X
        to: $F
      # Joining or normalising keeps what the caller sent: os.path.join(root, "/etc/passwd") drops root, '..'
      # survives normpath and abspath, and urljoin(base, "http://elsewhere/") drops base.
      - by-side-effect: false
        patterns:
          - pattern: $F(..., $X, ...)
          - metavariable-pattern:
              metavariable: $F
              patterns:
                - pattern-either:
""" + "".join(f"                    - pattern: {m}.{f}\n" for m in ("os.path", "posixpath", "ntpath")
              for f in ("join", "normpath", "abspath", "realpath", "expanduser")) + """\
                    - pattern: urllib.parse.urljoin
          - focus-metavariable: $F
        from: $X
        to: $F
"""


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


_CLIENT = "(?i).*(client|session|http).*"
# Methods whose first positional argument is the URL. `request(method, url)` and `stream(method, url)`
# are not among them: binding `$M` to either would treat the method string as the URL and miss the real one.
_URL_FIRST = "^(get|post|put|patch|delete|head|options)$"
# Calls that take the method first and the URL second. requests has no stream().
_URL_SECOND = ("request", "stream")
_URL_SECOND_CALLS = ("requests.request", "httpx.request", "httpx.stream")


def _url_calls(arg: str) -> str:
    """`- pattern-either:` over the outbound calls, with `arg` as the URL.

    `get`/`post`/etc take the URL first, and so does `url=`. `request(method, url)`, `stream(method, url)`
    and the same two on a client take it second, and `Client.request(method=..., url=...)` names both.
    `urlopen(url=...)` is the keyword form of both urlopen spellings.
    """
    out = ["          - pattern-either:"]
    for call in ("requests.$M", "httpx.$M"):
        out += [
            "              - patterns:",
            f"                  - pattern: {call}({arg}, ...)",
            "                  - metavariable-regex:",
            "                      metavariable: $M",
            f"                      regex: {_URL_FIRST}",
            f"              - pattern: {call}(url={arg}, ...)",
        ]
    for call in _URL_SECOND_CALLS:
        out.append(f"              - pattern: {call}($METHOD, {arg}, ...)")
        out.append(f"              - pattern: {call}($METHOD, url={arg}, ...)")
    for call in ("urllib.request.urlopen", "urlopen"):
        out.append(f"              - pattern: {call}({arg}, ...)")
        out.append(f"              - pattern: {call}(url={arg}, ...)")
    out += [
        "              - patterns:",
        "                  - pattern-either:",
        f"                      - pattern: $C.$M({arg}, ...)",
        f"                      - pattern: $C.$M(url={arg}, ...)",
        "                  - metavariable-regex:",
        "                      metavariable: $C",
        f"                      regex: {_CLIENT}",
        "                  - metavariable-regex:",
        "                      metavariable: $M",
        f"                      regex: {_URL_FIRST}",
        "              - patterns:",
        "                  - pattern-either:",
        *(f"                      - pattern: $C.{m}({a}, ...)" for m in _URL_SECOND
          # The last is all keywords: a positional $METHOD never binds a `method=` keyword.
          for a in (f"$METHOD, {arg}", f"$METHOD, url={arg}", f"url={arg}")),
        "                  - metavariable-regex:",
        "                      metavariable: $C",
        f"                      regex: {_CLIENT}",
    ]
    return "\n".join(out)


TEMPLATES = ('f"..."', "$A + $B", "$S.format(...)")

# A literal prefix pins the host only when it is scheme, host and a slash. Anything short of that
# (`https://api.internal` + user, `f"https://{host}/x"`, `"http://{}".format(host)`) still chooses it.
_PINNED_PREFIX = r"""^[rRbBuU]*["'][a-zA-Z][a-zA-Z0-9+.-]*://[^/"'{]+/"""
_SLASH_LITERAL = r"""^[rRbBuU]*["']/"""
# Literal text that does not end the authority: anything but a slash, or the `://` after the scheme.
_LIT = r"""(?:[^/{}"']|://)"""
# How many holes or placeholders ahead of the tainted one are told apart. Past that it is not a sink.
_HOLES = 4


def _unpinned_format(i: int) -> str:
    """A format string whose placeholder for positional argument *i* comes before the slash that ends the authority.

    `"{}/users/{}".format(BASE, uid)` pins the host for `uid` but not for `BASE`; `"https://{}/x"`,
    `"{}://{}/x"` and `"https://api.{}/x"` pin nothing. The placeholder is the i-th `{}` or `{i}`.
    """
    auto = rf"""{_LIT}*(?:\{{[^{{}}]*\}}{_LIT}*){{{i}}}\{{(?:[!:][^{{}}]*)?\}}"""
    numbered = rf"""(?:{_LIT}|\{{[^{{}}]*\}})*\{{{i}(?:[!:.\[][^{{}}]*)?\}}"""
    return rf"""^[rRbBuU]*["'](?:{auto}|{numbered})"""


def _unpinned_fstring(k: int) -> str:
    """An f-string hole in the authority, with *k* holes between `://` and it. The hole is bound as $U.

    The hole has to be the one in the authority: `f"https://{HOST}/users/{uid}"` puts `uid` in the path.
    """
    return rf"""://[^/"'{{}}]*(?:\{{[^{{}}]*\}}[^/"'{{}}]*){{{k}}}\{{(?P<U>[^{{}}]+)\}}"""


def _right_concat() -> str:
    """`$L + $U` is a sink unless `$L` ends the authority, or a `"/..."` literal already closed it."""
    return f"""          - metavariable-pattern:
              metavariable: $ARG
              patterns:
                - pattern: $L + $U
                - pattern-not:
                    patterns:
                      - pattern: $L + $U
                      - metavariable-regex:
                          metavariable: $L
                          regex: {json.dumps(_PINNED_PREFIX)}
                - pattern-not:
                    patterns:
                      - pattern: ($A + $S) + $U
                      - metavariable-regex:
                          metavariable: $S
                          regex: {json.dumps(_SLASH_LITERAL)}
          - focus-metavariable: $U"""


URL_SINKS = "\n".join([
    """    pattern-sinks:
      # The URL itself is a sink. A template is too, unless a constant prefix ends the authority
      # (scheme, host and a slash). `f"https://{host}/x"`, `"http://{}".format(host)` and
      # `BASE + user` still choose the host; `f"https://api.example.com/{id}"` does not.
      - patterns:""",
    _url_calls("$U"),
    *(f"          - pattern-not: $F({kw}{t}, ...)" for t in TEMPLATES for kw in ("", "url=")),
    # request() and stream() hold the template second. Named, so a template body in `post(url, f"...")` is not one.
    *(f"          - pattern-not: $O.{m}($METHOD, {t}, ...)" for t in TEMPLATES for m in _URL_SECOND),
    """          - focus-metavariable: $U
      # A template whose tainted part leads (f"{U}/api", U + "/x").
      - patterns:""",
    _url_calls("$ARG"),
    """          - metavariable-pattern:
              metavariable: $ARG
              pattern-either:
                - pattern: f"{$U}..."
                - pattern: $U + $R
          - focus-metavariable: $U
      # An f-string hole before the authority-ending slash (f"https://{host}/x", f"https://api.{host}/x").
      - patterns:""",
    _url_calls("$ARG"),
    """          - metavariable-pattern:
              metavariable: $ARG
              patterns:
                - pattern: f"..."
                - pattern-either:""",
    *(f"                    - pattern-regex: {json.dumps(_unpinned_fstring(k))}" for k in range(_HOLES)),
    """          - focus-metavariable: $U
      # Appended on the right: a sink unless the left side provably ends the authority.
      - patterns:""",
    _url_calls("$ARG"),
    _right_concat(),
    # format(): the argument whose placeholder is not after a prefix that ends the authority.
    *(part for i in range(_HOLES) for part in (
        "      - patterns:",
        _url_calls(f"$S.format({'$_, ' * i}$U, ...)"),
        f"""          - metavariable-regex:
              metavariable: $S
              regex: {json.dumps(_unpinned_format(i))}
          - focus-metavariable: $U""")),
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
            f"{EXCLUDE}\n{sources()}\n{SANITIZERS}\n{PROPAGATORS}\n{sinks}\n")


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
