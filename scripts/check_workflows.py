#!/usr/bin/env python3
"""Checks this repo's own workflows. Every consumer pins a major tag (@v1), so a reusable workflow's
inputs and secrets are a public API.

Hygiene, for every workflow here: a top-level `permissions:` block (least privilege, inherited by
every caller of a reusable workflow) and no `pull_request_target` trigger.

Compatibility: compares each `on: workflow_call` workflow in the working tree with the same file at BASE (default
`v1`) and fails on a change that breaks a caller:

  * a workflow, input or secret removed (or renamed, which is the same thing to a caller);
  * an input's type changed;
  * an input or secret that becomes required, or a new one that is required without a default.

A changed default is printed as a warning: callers keep working, but behave differently.

A deliberate break belongs in a new major. Change BASE in self-check.yml to that major's tag in the
same PR, so the break is visible in review, and never move the old tag over it.

Usage: check_workflows.py [BASE]   (needs PyYAML and the BASE tag fetched)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

WORKFLOWS = Path(".github/workflows")


def _call(doc: object) -> dict | None:
    if not isinstance(doc, dict):
        return None
    on = doc.get("on", doc.get(True))  # YAML 1.1 reads a bare `on` key as True
    if isinstance(on, dict) and "workflow_call" in on:
        return on["workflow_call"] or {}
    # Shorthand forms: `on: workflow_call` and `on: [workflow_call, push]` (no inputs or secrets).
    if on == "workflow_call" or (isinstance(on, list) and "workflow_call" in on):
        return {}
    return None


def _at(base: str, path: Path) -> dict | None:
    r = subprocess.run(["git", "show", f"{base}:{path.as_posix()}"], capture_output=True, text=True)
    return _call(yaml.safe_load(r.stdout)) if r.returncode == 0 else None


def _required(spec: dict) -> bool:
    return bool(spec.get("required")) and "default" not in spec


def compare(name: str, old: dict, new: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for kind in ("inputs", "secrets"):
        o, n = old.get(kind) or {}, new.get(kind) or {}
        for key, spec in o.items():
            spec = spec or {}
            if key not in n:
                errors.append(f"{name}: {kind[:-1]} `{key}` was removed or renamed")
                continue
            ns = n[key] or {}
            if kind == "inputs" and spec.get("type") != ns.get("type"):
                errors.append(f"{name}: input `{key}` changed type {spec.get('type')} -> {ns.get('type')}")
            if _required(ns) and not _required(spec):
                errors.append(f"{name}: {kind[:-1]} `{key}` became required")
            if kind == "inputs" and spec.get("default") != ns.get("default"):
                warnings.append(f"{name}: input `{key}` default changed {spec.get('default')!r} -> {ns.get('default')!r}")
        for key in n.keys() - o.keys():
            if _required(n[key] or {}):
                errors.append(f"{name}: new {kind[:-1]} `{key}` is required (give it a default, or required: false)")
    return errors, warnings


def hygiene(name: str, doc: object) -> list[str]:
    if not isinstance(doc, dict):
        return [f"{name}: not a workflow mapping"]
    out = []
    if "permissions" not in doc:
        out.append(f"{name}: no top-level `permissions:` block (start from `contents: read`)")
    on = doc.get("on", doc.get(True))
    triggers = on if isinstance(on, (dict, list)) else [on]
    if "pull_request_target" in triggers:
        out.append(f"{name}: `pull_request_target` runs fork code with secrets; use `pull_request`")
    return out


def main(base: str) -> int:
    if subprocess.run(["git", "rev-parse", "--verify", "-q", f"{base}^{{commit}}"], capture_output=True).returncode:
        print(f"::error::{base} is not fetched; check out with fetch-depth: 0 (tags included)")
        return 2
    listed = subprocess.run(["git", "ls-tree", "--name-only", f"{base}:{WORKFLOWS.as_posix()}"],
                            capture_output=True, text=True).stdout.split()
    errors, warnings = [], []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        errors += hygiene(path.name, yaml.safe_load(path.read_text(encoding="utf-8")))
    for fname in sorted(listed):
        path = WORKFLOWS / fname
        old = _at(base, path)
        if old is None:
            continue
        if not path.is_file():
            errors.append(f"{fname}: a reusable workflow at {base} was removed")
            continue
        new = _call(yaml.safe_load(path.read_text(encoding="utf-8")))
        if new is None:
            errors.append(f"{fname}: no longer `on: workflow_call`")
            continue
        e, w = compare(fname, old, new)
        errors += e
        warnings += w
    for w in warnings:
        print(f"::warning::{w}")
    for e in errors:
        print(f"::error::{e}")
    print(f"{len(errors)} breaking change(s), {len(warnings)} warning(s) against {base}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "v1"))
