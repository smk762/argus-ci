#!/usr/bin/env python3
"""Suite rules: scan a repo with the catalogue, keep a shrinking baseline, prove the rules.

    python check.py scan     [--root .] [--json]
    python check.py baseline [--root .] [--write .suite-rules-baseline.json]
    python check.py check    [--root .] [--baseline .suite-rules-baseline.json] [--base-baseline FILE]
    python check.py fixtures [--json]
    python check.py prompts  [--root .] [--allowlist .suite-prompts-allowlist.txt] [--write] [paths ...]

Standard library only (Python 3.11+). ruff and semgrep come from $RUFF and $SEMGREP (default:
``ruff`` / ``semgrep`` on PATH), so CI can pin them: RUFF="uvx ruff@0.15.16".

A hit is keyed by rule, file and the normalised text of its line, not its line number, so code
moving around doesn't turn old hits into new ones. The baseline counts hits per key.
``check`` fails when a key appears more often than the baseline allows (a new violation), and,
given the base branch's baseline, when the baseline itself grew (the ratchet only shrinks). The
ratchet compares each rule's total, not each key, so renaming a file or editing a line that holds a
baselined hit (a new key, same count) passes once the baseline is regenerated. A baseline records the
rules it was written with: a rule the base branch's baseline has never seen may enter the baseline
once, with the hits it finds on adoption, and is ratcheted from then on.

``prompts`` holds every prompt a repo's tests send to a reviewed allowlist (#20): the string given
to a ``prompt`` / ``user_prompt`` / ``negative_prompt`` / ``negative`` keyword, dict key or variable
in a test file, and the same keys in ``*.jsonl`` under tests/ or eval/. A new prompt fails until it
is added to ``.suite-prompts-allowlist.txt``, so it is reviewed as its own line in the diff.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOGUE = HERE / "catalogue.toml"
BASELINE = ".suite-rules-baseline.json"
EXCLUDE = ("tests", "test", "fixtures", ".venv", "venv", "node_modules", "build", "dist", ".git", ".argus-ci")


@dataclass(frozen=True)
class Rule:
    id: str
    cls: str
    tool: str
    severity: str
    message: str
    codes: tuple[str, ...] = ()
    kind: str = "guard"

    @property
    def semgrep_config(self) -> Path:
        return HERE / "semgrep" / f"{self.id}.yml"


@dataclass
class Hit:
    rule: str
    path: str
    line: int
    text: str
    detail: str = ""

    @property
    def key(self) -> str:
        return f"{self.rule}|{self.path}|{self.text}"


def load_rules(path: Path = CATALOGUE) -> tuple[list[Rule], dict[str, str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    rules = []
    for r in data["rules"]:
        rule = Rule(id=r["id"], cls=r["class"], tool=r["tool"], severity=r.get("severity", "MEDIUM"),
                    message=r["message"], codes=tuple(r.get("codes") or ()), kind=r.get("kind", "guard"))
        if rule.kind not in ("guard", "convention"):
            raise ValueError(f"{rule.id}: kind must be guard or convention")
        if rule.tool == "ruff" and not rule.codes:
            raise ValueError(f"{rule.id}: a ruff rule needs codes")
        if rule.tool == "semgrep" and not rule.semgrep_config.is_file():
            raise ValueError(f"{rule.id}: missing {rule.semgrep_config.relative_to(HERE)}")
        if rule.tool not in ("ruff", "semgrep"):
            raise ValueError(f"{rule.id}: unknown tool {rule.tool}")
        rules.append(rule)
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate rule ids")
    return rules, dict(data.get("tools") or {})


def _cmd(env: str, default: str) -> list[str]:
    return shlex.split(os.environ.get(env) or default)


def _line(root: Path, rel: str, n: int) -> str:
    try:
        lines = (root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return " ".join(lines[n - 1].split()) if 0 < n <= len(lines) else ""


def _targets(root: Path, paths: list[str]) -> list[str]:
    return paths or ["."]


def run_ruff(rules: list[Rule], root: Path, paths: list[str], *, exclude: tuple[str, ...] = EXCLUDE) -> list[Hit]:
    by_code = {c: r for r in rules if r.tool == "ruff" for c in r.codes}
    if not by_code:
        return []
    cmd = [*_cmd("RUFF", "ruff"), "check", "--isolated", "--no-cache", "--exit-zero", "--output-format", "json",
           "--select", ",".join(sorted(by_code))]
    if exclude:
        cmd += ["--extend-exclude", ",".join(exclude)]
    r = subprocess.run([*cmd, *_targets(root, paths)], cwd=root, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"ruff failed: {r.stderr.strip()[:500]}")
    hits = []
    for d in json.loads(r.stdout or "[]"):
        rule = by_code.get(d.get("code") or "")
        if rule is None:
            continue
        rel = os.path.relpath(d["filename"], root)
        n = int((d.get("location") or {}).get("row") or 0)
        hits.append(Hit(rule.id, rel, n, _line(root, rel, n), f"{d.get('code')}: {d.get('message', '')}"))
    return hits


# service-peer-label's helper rule (same semgrep file) reports the compose services that carry argus.peer.
# Compose merges files by service name, so an entry in an overlay (compose.build.yaml, compose.gpu.yaml) for a
# service that a compose file in the same directory labels is that same container, not an unlabelled one.
PEER_LABEL, PEER_LABELLED = "service-peer-label", "service-peer-labelled"


def _compose_service(rel: str, text: str) -> tuple[str, str]:
    """(directory, service name) for a hit on a compose service's key line."""
    return os.path.dirname(rel), text.split(":", 1)[0].strip().strip("'\"")


def run_semgrep(rules: list[Rule], root: Path, paths: list[str], *, exclude: tuple[str, ...] = EXCLUDE) -> list[Hit]:
    sem = [r for r in rules if r.tool == "semgrep"]
    if not sem:
        return []
    cmd = [*_cmd("SEMGREP", "semgrep"), "scan", "--json", "--metrics", "off", "--quiet", "--disable-version-check",
           "--no-git-ignore"]
    for r in sem:
        cmd += ["--config", str(r.semgrep_config)]
    for e in exclude:
        cmd += ["--exclude", e]
    r = subprocess.run([*cmd, *_targets(root, paths)], cwd=root, capture_output=True, text=True, check=False)
    if r.returncode not in (0, 1):
        raise RuntimeError(f"semgrep failed ({r.returncode}): {r.stderr.strip()[:500]}")
    ids = {x.id for x in sem}
    hits = []
    labelled: set[tuple[str, str]] = set()
    for res in json.loads(r.stdout or "{}").get("results") or []:
        rid = str(res.get("check_id") or "").rsplit(".", 1)[-1]
        rel = os.path.relpath(os.path.join(root, res["path"]), root)
        n = int((res.get("start") or {}).get("line") or 0)
        if rid == PEER_LABELLED:
            labelled.add(_compose_service(rel, _line(root, rel, n)))
        if rid not in ids:
            continue
        hits.append(Hit(rid, rel, n, _line(root, rel, n), " ".join(str((res.get("extra") or {}).get("message", "")).split())))
    return [h for h in hits if not (h.rule == PEER_LABEL and _compose_service(h.path, h.text) in labelled)]


def scan(root: Path, paths: list[str] | None = None, *, rules: list[Rule] | None = None,
         exclude: tuple[str, ...] = EXCLUDE) -> list[Hit]:
    rules = rules if rules is not None else load_rules()[0]
    hits = run_ruff(rules, root, paths or [], exclude=exclude) + run_semgrep(rules, root, paths or [], exclude=exclude)
    return sorted(hits, key=lambda h: (h.path, h.line, h.rule))


def counts(hits: list[Hit]) -> Counter[str]:
    return Counter(h.key for h in hits)


def read_baseline(path: Path) -> Counter[str]:
    if not path.is_file():
        return Counter()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Counter({f"{e['rule']}|{e['path']}|{e['text']}": int(e.get("count", 1)) for e in data.get("entries") or []})


# The catalogue when baselines did not yet record their rules: what a baseline with no "rules" list knows.
RULES_BEFORE_RECORDING = frozenset({
    "missing-timeout", "silent-except", "predictable-tmp", "request-path-to-fs", "request-url-outbound",
    "token-compare", "agpl-import", "blocking-in-async", "handler-scans-all", "sibling-checkout-read", "cortex-copy",
})


def baseline_rules(path: Path) -> frozenset[str] | None:
    """The rules the baseline at *path* was written with; None when there is no baseline."""
    if not path.is_file():
        return None
    known = json.loads(path.read_text(encoding="utf-8")).get("rules")
    return frozenset(str(r) for r in known) if isinstance(known, list) else RULES_BEFORE_RECORDING


def write_baseline(path: Path, hits: list[Hit], tools: dict[str, str], rules: list[str] | None = None) -> int:
    c = counts(hits)
    entries = []
    for key, n in sorted(c.items()):
        rule, rel, text = key.split("|", 2)
        entries.append({"rule": rule, "path": rel, "text": text, "count": n})
    data: dict = {"version": 1, "tools": tools}
    if rules is not None:
        data["rules"] = sorted(rules)
    data["entries"] = entries
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return sum(c.values())


def _per_rule(c: Counter[str]) -> Counter[str]:
    out: Counter[str] = Counter()
    for key, n in c.items():
        out[key.split("|", 1)[0]] += n
    return out


def compare(hits: list[Hit], baseline: Counter[str], base: Counter[str] | None = None,
            base_rules: frozenset[str] | None = None) -> dict:
    """New hits beyond the baseline, entries now fixed, and (given the base branch's baseline) the
    rules whose baselined total grew. Totals per rule, not per key: a renamed file or an edited line
    moves a hit to a new key without adding one. Given *base_rules*, the rules the base branch's
    baseline was written with, a rule outside them is new to the repo and may enter the baseline."""
    cur = counts(hits)
    new = []
    seen: Counter[str] = Counter()
    for h in hits:
        seen[h.key] += 1
        if seen[h.key] > baseline.get(h.key, 0):
            new.append(h)
    fixed = sum(max(0, n - cur.get(k, 0)) for k, n in baseline.items())
    grew = []
    if base is not None:
        mine, theirs = _per_rule(baseline), _per_rule(base)
        grew = sorted(r for r, n in mine.items()
                      if n > theirs.get(r, 0) and (base_rules is None or r in base_rules))
    return {"new": new, "fixed": fixed, "grew": grew}


def _fixture_files(d: Path, prefix: str) -> list[Path]:
    return sorted(p for p in d.glob(f"{prefix}*") if p.is_file())


def fixtures(rules: list[Rule] | None = None) -> list[dict]:
    """Every rule must fire on each fixtures/<id>/positive.* file and stay silent on every negative.*."""
    rules = rules if rules is not None else load_rules()[0]
    out = []
    for r in rules:
        d = HERE / "fixtures" / r.id
        pos, neg = _fixture_files(d, "positive"), _fixture_files(d, "negative")
        res = {"rule": r.id, "class": r.cls, "kind": r.kind, "tool": r.tool, "ok": False, "positive_hits": 0, "negative_hits": 0,
               "note": ""}
        if not pos or not neg:
            res["note"] = "needs a positive and a negative fixture"
            out.append(res)
            continue
        try:
            hp = [h for h in scan(d, [p.name for p in pos], rules=[r], exclude=()) if h.rule == r.id]
            hn = [h for h in scan(d, [p.name for p in neg], rules=[r], exclude=()) if h.rule == r.id]
        except (RuntimeError, OSError, ValueError) as exc:
            res["note"] = str(exc)[:300]
            out.append(res)
            continue
        fired = {Path(h.path).as_posix() for h in hp}
        silent = [p.name for p in pos if p.name not in fired]
        res.update(positive_hits=len(hp), negative_hits=len(hn), ok=not silent and not hn,
                   negative_lines=[h.line for h in hn], silent_positives=silent)
        if silent:
            res["note"] = f"silent on positive fixture(s): {', '.join(silent)}"
        elif hn:
            res["note"] = f"fires on its negative fixture (lines {', '.join(str(h.line) for h in hn)})"
        out.append(res)
    return out


PROMPT_ALLOWLIST = ".suite-prompts-allowlist.txt"
PROMPT_NAME = re.compile(r"(^|_)(prompts?|negative)$", re.IGNORECASE)
_SKIP_DIRS = {".venv", "venv", "node_modules", "build", "dist", ".git", ".argus-ci", "__pycache__"}


def _is_test(rel: Path) -> bool:
    n = rel.name
    return (any(p in ("tests", "test") for p in rel.parts[:-1]) or n.startswith("test_")
            or n.endswith("_test.py") or n == "conftest.py")


def _norm(s: str) -> str:
    return " ".join(s.split())


def _strings(node: ast.AST):
    """String literals in *node*: a str constant, an f-string (each placeholder as ``{}``), or a
    list/tuple/set of those."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.JoinedStr):
        yield "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for e in node.elts:
            yield from _strings(e)


def _target_name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def prompts_in_py(text: str) -> list[str]:
    """Prompts in Python source: values of prompt-named keywords, dict keys and assignments."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out = []
    for n in ast.walk(tree):
        pairs: list[tuple[str, ast.AST]] = []
        if isinstance(n, ast.keyword) and n.arg:
            pairs.append((n.arg, n.value))
        elif isinstance(n, ast.Dict):
            pairs += [(_target_name(k), v) for k, v in zip(n.keys, n.values) if k is not None]
        elif isinstance(n, ast.Assign):
            pairs += [(_target_name(t), n.value) for t in n.targets]
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            pairs.append((_target_name(n.target), n.value))
        for name, value in pairs:
            if PROMPT_NAME.search(name):
                out += [_norm(s) for s in _strings(value) if s.strip()]
    return out


def prompts_in_jsonl(text: str) -> list[str]:
    """Prompts in JSON Lines: values of prompt-named keys. ``//`` comment lines are skipped."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out += [_norm(v) for k, v in row.items() if PROMPT_NAME.search(k) and isinstance(v, str) and v.strip()]
    return out


def _walk(root: Path) -> list[Path]:
    """The .py and .jsonl files under *root*, never descending into _SKIP_DIRS (node_modules alone
    can hold hundreds of thousands of files)."""
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in _SKIP_DIRS]
        out += [Path(d, f) for f in files if f.endswith((".py", ".jsonl"))]
    return sorted(out)


def collect_prompts(root: Path, paths: list[str] | None = None) -> dict[str, list[str]]:
    """Prompt -> files it appears in: test files and eval/test JSONL under *root*, plus every .py
    and .jsonl under *paths* (relative to *root*), test or not."""
    found: dict[str, list[str]] = {}
    extra = [(root / p).resolve() for p in paths or []]
    for f in _walk(root):
        rel = f.relative_to(root)
        listed = any(f.resolve() == e or e in f.resolve().parents for e in extra)
        if f.suffix == ".py" and (listed or _is_test(rel)):
            got = prompts_in_py(f.read_text(encoding="utf-8", errors="replace"))
        elif f.suffix == ".jsonl" and (listed or _is_test(rel) or "eval" in rel.parts[:-1]):
            got = prompts_in_jsonl(f.read_text(encoding="utf-8", errors="replace"))
        else:
            continue
        for s in got:
            files = found.setdefault(s, [])
            if rel.as_posix() not in files:
                files.append(rel.as_posix())
    return found


def read_allowlist(path: Path) -> set[str]:
    """One prompt per line; blank lines and lines starting with ``#`` are ignored. A prompt that
    itself starts with ``#`` or ``\\`` is written with a leading ``\\``, which is dropped here."""
    if not path.is_file():
        return set()
    return {_norm(ln[1:] if ln.startswith("\\") else ln) for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def _escape(prompt: str) -> str:
    return "\\" + prompt if prompt.startswith(("#", "\\")) else prompt


def write_allowlist(path: Path, prompts: list[str]) -> None:
    head = ("# Every prompt this repo's tests send (argus-ci suite-rules `check.py prompts`, #20).\n"
            "# Harmless markers only: no sexual, violent or illegal text. One prompt per line, whitespace\n"
            "# collapsed; review each new line as you would the prompt itself.\n")
    path.write_text(head + "".join(f"{_escape(p)}\n" for p in sorted(set(prompts))), encoding="utf-8")


def _print_hits(hits: list[Hit]) -> None:
    for h in hits:
        print(f"{h.path}:{h.line}: [{h.rule}] {h.detail}")


def _prompts(root: Path, allowlist: str, write: bool, paths: list[str]) -> int:
    found = collect_prompts(root, paths)
    path = root / allowlist
    if write:
        write_allowlist(path, list(found))
        print(f"wrote {len(found)} prompt(s) to {allowlist}")
        return 0
    allowed = read_allowlist(path)
    new = {p: fs for p, fs in found.items() if p not in allowed}
    for p, fs in sorted(new.items()):
        print(f"{fs[0]}: prompt not in {allowlist}: {p!r}")
    unused = allowed - found.keys()
    if unused:
        print(f"{len(unused)} allowlisted prompt(s) are no longer used: run `check.py prompts --write` to drop them.")
    if new:
        print(f"{len(new)} prompt(s) are not in {allowlist}. If each is a harmless marker, add it there "
              "(one line each) so review sees it.")
        return 1
    print(f"ok: {len(found)} prompt(s), all allowlisted")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "baseline", "check"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        p.add_argument("paths", nargs="*")
        p.add_argument("--json", action="store_true")
    sub.choices["baseline"].add_argument("--write", default=BASELINE)
    sub.choices["check"].add_argument("--baseline", default=BASELINE)
    sub.choices["check"].add_argument("--base-baseline", default="",
                                      help="The base branch's baseline: the baseline may not grow past it")
    pr = sub.add_parser("prompts", help="Hold the prompts tests send to a reviewed allowlist")
    pr.add_argument("--root", default=".")
    pr.add_argument("--allowlist", default=PROMPT_ALLOWLIST)
    pr.add_argument("--write", action="store_true", help="Write the allowlist from the prompts found (adoption)")
    pr.add_argument("paths", nargs="*", help="Extra files or dirs to scan in full, test or not (e.g. demo/)")
    fx = sub.add_parser("fixtures")
    fx.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "prompts":
        return _prompts(Path(a.root).resolve(), a.allowlist, a.write, a.paths)
    if a.cmd == "fixtures":
        res = fixtures()
        if a.json:
            print(json.dumps(res, indent=1))
        else:
            for r in res:
                print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['rule']:<24} +{r['positive_hits']} -{r['negative_hits']} {r['note']}")
        return 0 if all(r["ok"] for r in res) else 1

    root = Path(a.root).resolve()
    if not root.is_dir():
        print(f"no such directory: {root}", file=sys.stderr)
        return 2
    rules, tools = load_rules()
    hits = scan(root, a.paths, rules=rules)
    if a.cmd == "scan":
        if a.json:
            meta = {r.id: {"class": r.cls, "kind": r.kind, "severity": r.severity, "message": r.message, "tool": r.tool}
                    for r in rules}
            print(json.dumps({"rules": meta, "hits": [asdict(h) for h in hits]}, indent=1))
        else:
            _print_hits(hits)
            print(f"{len(hits)} hits")
        return 0
    if a.cmd == "baseline":
        n = write_baseline(root / a.write, hits, tools, [r.id for r in rules])
        print(f"wrote {n} hits to {a.write}")
        return 0
    base = read_baseline(Path(a.base_baseline)) if a.base_baseline else None
    base_rules = baseline_rules(Path(a.base_baseline)) if a.base_baseline else None
    rep = compare(hits, read_baseline(root / a.baseline), base, base_rules)
    by_rule = {r.id: r for r in rules}
    if rep["new"]:
        print(f"{len(rep['new'])} new suite-rule violation(s):")
        for h in rep["new"]:
            r = by_rule[h.rule]
            print(f"  {h.path}:{h.line}: [{h.rule}] {r.message}")
        print("Fix them, or mark a line with a reasoned `# noqa: <code>` / `# nosemgrep: <id>`.")
    if rep["grew"]:
        print(f"The baseline grew for {len(rep['grew'])} rule(s) compared with the base branch "
              f"({', '.join(rep['grew'])}); it may only shrink.")
    if rep["fixed"]:
        print(f"{rep['fixed']} baselined hit(s) are fixed: run `check.py baseline` to shrink the baseline.")
    if not rep["new"] and not rep["grew"]:
        print(f"ok: {len(hits)} hit(s), all in the baseline")
    return 1 if rep["new"] or rep["grew"] else 0


if __name__ == "__main__":
    sys.exit(main())
