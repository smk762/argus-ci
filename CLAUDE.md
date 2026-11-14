# CLAUDE.md — argus-ci

Guidance for AI agents working in this repo. Human-facing usage lives in [README.md](README.md); this file is the orientation an agent needs to change these workflows safely.

## What this is

**Not a package** — no `src/`, no `pyproject.toml`, no tests to run here. This repo is the shared **reusable GitHub Actions workflows** for the Argus suite. One place to define the `uv` + `ruff` + `pytest` + `build` pipeline so every downstream repo stays in lockstep instead of drifting.

Editing a file here changes CI for **every consumer at once**. The contract you are maintaining is the set of `workflow_call` inputs and the steps they drive — treat inputs like a public API.

## Argus suite
<!-- argus-suite: keep this block; argus-ci checks for it -->
This repo is part of the Argus suite. The suite map below lists every sibling and what it owns; check it before
building something a sibling may already do. **On every release, update this repo's row and capabilities in
argus-cortex's SUITE.md** (a PR to argus-cortex in the same release).

@../argus-core/SUITE.md

Not checked out? Read https://github.com/smk762/argus-cortex/blob/dev/SUITE.md

## Layout

```
.github/workflows/
  python-ci.yml     # reusable Python pipeline (`on: workflow_call`)
  suite-check.yml   # reusable suite-map check: CLAUDE.md block + SUITE.md row (`on: workflow_call`)
  suite.yml         # this repo's own caller of suite-check.yml
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

## Branches

`dev` is the default branch and the base for every PR. Cut feature branches from `origin/dev` and bring them up to date by merging `origin/dev`, never `main`. Never open a PR against `main` or push work to it directly: `main` must never be ahead of `dev`. A release fast-forwards `main` to a `dev` commit that passed CI (`git push origin origin/dev:main`), then tags it. If `main` is protected and needs a PR, merge the release PR, then immediately merge `main` back into `dev` so the merge commit is not left on `main` alone.
