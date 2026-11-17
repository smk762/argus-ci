#!/usr/bin/env python3
"""Suite rules: scan a repo with the catalogue, keep a shrinking baseline, prove the rules.

    python check.py scan     [--root .] [--json]
    python check.py baseline [--root .] [--write .suite-rules-baseline.json]
    python check.py check    [--root .] [--baseline .suite-rules-baseline.json] [--base-baseline FILE]
    python check.py fixtures [--json]

Standard library only (Python 3.11+). ruff and semgrep come from $RUFF and $SEMGREP (default:
``ruff`` / ``semgrep`` on PATH), so CI can pin them: RUFF="uvx ruff@0.15.16".

A hit is keyed by rule, file and the normalised text of its line, not its line number, so code
moving around doesn't turn old hits into new ones. The baseline counts hits per key.
``check`` fails when a key appears more often than the baseline allows (a new violation), and,
given the base branch's baseline, when the baseline itself grew (the ratchet only shrinks).
"""
from __future__ import annotations

import argparse
import json
import os
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
    for res in json.loads(r.stdout or "{}").get("results") or []:
        rid = str(res.get("check_id") or "").rsplit(".", 1)[-1]
        if rid not in ids:
            continue
        rel = os.path.relpath(os.path.join(root, res["path"]), root)
        n = int((res.get("start") or {}).get("line") or 0)
        hits.append(Hit(rid, rel, n, _line(root, rel, n), " ".join(str((res.get("extra") or {}).get("message", "")).split())))
    return hits


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


def write_baseline(path: Path, hits: list[Hit], tools: dict[str, str]) -> int:
    c = counts(hits)
    entries = []
    for key, n in sorted(c.items()):
        rule, rel, text = key.split("|", 2)
        entries.append({"rule": rule, "path": rel, "text": text, "count": n})
    path.write_text(json.dumps({"version": 1, "tools": tools, "entries": entries}, indent=1) + "\n", encoding="utf-8")
    return sum(c.values())


def compare(hits: list[Hit], baseline: Counter[str], base: Counter[str] | None = None) -> dict:
    """New hits beyond the baseline, entries now fixed, and (given the base branch's baseline)
    entries the baseline gained."""
    cur = counts(hits)
    new = []
    seen: Counter[str] = Counter()
    for h in hits:
        seen[h.key] += 1
        if seen[h.key] > baseline.get(h.key, 0):
            new.append(h)
    fixed = sum(max(0, n - cur.get(k, 0)) for k, n in baseline.items())
    grew = sorted(k for k, n in baseline.items() if n > (base or Counter()).get(k, 0)) if base is not None else []
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


def _print_hits(hits: list[Hit]) -> None:
    for h in hits:
        print(f"{h.path}:{h.line}: [{h.rule}] {h.detail}")


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
    fx = sub.add_parser("fixtures")
    fx.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

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
        n = write_baseline(root / a.write, hits, tools)
        print(f"wrote {n} hits to {a.write}")
        return 0
    base = read_baseline(Path(a.base_baseline)) if a.base_baseline else None
    rep = compare(hits, read_baseline(root / a.baseline), base)
    by_rule = {r.id: r for r in rules}
    if rep["new"]:
        print(f"{len(rep['new'])} new suite-rule violation(s):")
        for h in rep["new"]:
            r = by_rule[h.rule]
            print(f"  {h.path}:{h.line}: [{h.rule}] {r.message}")
        print("Fix them, or mark a line with a reasoned `# noqa: <code>` / `# nosemgrep: <id>`.")
    if rep["grew"]:
        print(f"The baseline grew by {len(rep['grew'])} entr(ies) compared with the base branch; it may only shrink.")
    if rep["fixed"]:
        print(f"{rep['fixed']} baselined hit(s) are fixed: run `check.py baseline` to shrink the baseline.")
    if not rep["new"] and not rep["grew"]:
        print(f"ok: {len(hits)} hit(s), all in the baseline")
    return 1 if rep["new"] or rep["grew"] else 0


if __name__ == "__main__":
    sys.exit(main())
