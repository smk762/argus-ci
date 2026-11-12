# argus-ci

Shared, reusable GitHub Actions workflows for the [Argus suite](https://github.com/smk762?tab=repositories&q=argus)
(the map of every repo is [argus-cortex's SUITE.md](https://github.com/smk762/argus-cortex/blob/dev/SUITE.md)).

The goal is one place to define the `uv` + `ruff` + `pytest` + `build` pipeline so
every repo stays in lockstep instead of drifting.

## `python-ci.yml`

Reusable CI: lint (ruff), test matrix (pytest over an editable install), and a build
(`uv build`) that uploads the `dist/` artifact.

### Usage

Add a caller in the consuming repo at `.github/workflows/ci.yml`:

```yaml
name: CI
on:
  push:
    branches: [dev, main]
  pull_request:
    branches: [dev, main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    uses: smk762/argus-ci/.github/workflows/python-ci.yml@v1
    with:
      test-extras: "dev,server,cli"        # extras for the test install
      post-test: "uv run --no-sync argus-curator schema --check"  # optional
      # ruff-version: "0.15.16"            # optional pin
```

### Inputs

| Input             | Default              | Notes                                                        |
| ----------------- | -------------------- | ------------------------------------------------------------ |
| `python-versions` | `["3.11", "3.12"]`   | JSON array for the test matrix.                              |
| `test-extras`     | `dev`                | Extras installed before pytest, e.g. `dev,server,cli`.       |
| `ruff-version`    | `""`                 | Pin ruff via `uvx` (e.g. `0.15.16`); empty = latest.         |
| `lint-paths`      | `src/ tests/`        | Paths passed to `ruff check` / `ruff format --check`.        |
| `post-test`       | `""`                 | Extra command run in the test env after pytest.              |

## `suite-check.yml`

Keeps a repo on the [suite map](https://github.com/smk762/argus-cortex/blob/dev/SUITE.md) that agents
read. It fails when the repo's `CLAUDE.md` lacks the `<!-- argus-suite` block, or when `SUITE.md` has no
`| **<repo>** |` row. On a release tag it prints the row as a reminder to update it if the release changed
what the repo offers. It needs no toolchain, so UI repos use it too. Add `.github/workflows/suite.yml`:

```yaml
name: Suite
on:
  push:
    branches: [dev, main]
    tags: ["v*"]
  pull_request:
    branches: [dev, main]

jobs:
  suite:
    uses: smk762/argus-ci/.github/workflows/suite-check.yml@v1
```

Inputs: `repo-name` (default: the repository's name), `suite-url` (default: cortex `dev`).

## Why release/publish is **not** here

PyPI [trusted publishing cannot run inside a reusable workflow](https://docs.pypi.org/trusted-publishers/troubleshooting/#reusable-workflows-on-github)
(the OIDC `job_workflow_ref` check rejects it). So each repo keeps a **top-level**
`release.yml`. Its canonical form lives in
[`argus-pkg-template`](https://github.com/smk762/argus-pkg-template); run
`copier update` in a repo to re-sync it.

## Versioning

Callers pin a major tag (`@v1`). Breaking changes to inputs get a new major tag;
`v1` is kept moving to the latest backward-compatible commit.
