# CLAUDE.md — argus-ci

Guidance for AI agents working in this repo. Human-facing usage lives in [README.md](README.md); this file is the orientation an agent needs to change these workflows safely.

## What this is

**Not a package** — no `src/`, no `pyproject.toml`, no tests to run here. This repo is the shared **reusable GitHub Actions workflows** for the [Argus suite](https://github.com/smk762?tab=repositories&q=argus) (`argus-quarry` → `argus-curator` → `argus-lens`, orchestrated by `argus-studio`). One place to define the `uv` + `ruff` + `pytest` + `build` pipeline so every downstream repo stays in lockstep instead of drifting.

Editing a file here changes CI for **every consumer at once**. The contract you are maintaining is the set of `workflow_call` inputs and the steps they drive — treat inputs like a public API.

## Layout

```
.github/workflows/
  python-ci.yml   # the only reusable workflow (`on: workflow_call`)
README.md         # source of truth for the caller-facing usage + inputs table
```

`python-ci.yml` defines three jobs, all on `ubuntu-latest` via `astral-sh/setup-uv@v6` (cache enabled):

- **`lint`** — `uvx ruff check` + `ruff format --check` over `lint-paths`.
- **`test`** — matrix over `python-versions`; `uv venv` → `uv pip install -e ".[test-extras]"` → `uv run --no-sync pytest`; optional `post-test` command (e.g. a schema check) last. Checkout uses `fetch-depth: 0` so hatch-vcs can derive the dev version.
- **`build`** — `needs: [lint, test]`; `uv build` → uploads the `dist/` artifact (14-day retention).

Inputs (defaults): `python-versions` `["3.11","3.12"]`, `test-extras` `dev`, `ruff-version` `""` (latest), `lint-paths` `src/ tests/`, `post-test` `""`. See the README table for the authoritative descriptions.

## How it's consumed

Downstream repos add a thin caller at `.github/workflows/ci.yml` that pins a **major tag** and passes inputs:

```yaml
jobs:
  ci:
    uses: smk762/argus-ci/.github/workflows/python-ci.yml@v1
    with:
      test-extras: "dev,server,cli"
      post-test: "uv run --no-sync argus-curator schema --check"
```

There is no local test harness in this repo. To validate a workflow edit before pushing, lint it with [`actionlint`](https://github.com/rhysd/actionlint) (`actionlint .github/workflows/python-ci.yml`) and, ideally, dry-run the change from a real consumer's branch before moving the `v1` tag.

## Conventions & gotchas

- **Every change is a fleet change.** A broken step or a renamed/removed input breaks CI in all consumers simultaneously. Add inputs with safe defaults; treat removing or renaming one as breaking.
- **Versioning by moving major tags.** Consumers pin `@v1`. Backward-compatible changes: fast-forward `v1` to the new commit (`git tag -f v1 <sha> && git push -f origin v1`). Breaking input changes: cut a new `v2` and leave `v1` where it is.
- **No `secrets:` block today.** This workflow takes only `inputs:` — it needs no repo secrets and passes none through. If you add one, declare it under `workflow_call.secrets` and document that callers must forward it (`secrets: inherit` or explicit).
- **Release/publish is deliberately NOT here.** PyPI [trusted publishing (OIDC) cannot run inside a reusable workflow](https://docs.pypi.org/trusted-publishers/troubleshooting/#reusable-workflows-on-github) — the `job_workflow_ref` check rejects it. Each repo keeps a **top-level** `release.yml`; its canonical form lives in [`argus-pkg-template`](https://github.com/smk762/argus-pkg-template) (`copier update` to re-sync). Do not try to fold release into this file.
- **Ruff is unpinned by default** (`ruff-version: ""` → latest). Consumers wanting reproducible lint pass an explicit pin (e.g. `0.15.16`); the `format('@{0}', …)` expression wires that into the `uvx ruff@<ver>` invocation.
- **`uv run --no-sync`** everywhere — the editable install is already done in a prior step; `--no-sync` stops uv re-resolving and re-installing.
- **`post-test` runs arbitrary caller-supplied shell** in the test env by design (schema checks, extra gates). That's expected; keep it opt-in and empty by default.
- **Pin third-party actions to a major tag** (`@v4`, `@v6`) as the existing steps do; keep them consistent when bumping.
