# argus-ci

Shared, reusable GitHub Actions workflows for the [Argus suite](https://github.com/smk762?tab=repositories&q=argus)
(the map of every repo is [argus-cortex's SUITE.md](https://github.com/smk762/argus-cortex/blob/dev/SUITE.md)).

The goal is one place to define the `uv` + `ruff` + `pytest` + `build` pipeline so
every repo stays in lockstep instead of drifting.

How it fits with the package template, the schema gate and the image rebuilds, with the numbers from 1,347 CI runs:
[One release pipeline for sixteen packages](https://dragonhound.dev/updates/2026-11-27-one-release-pipeline/).

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
| `post-test`       | `""`                 | Extra command run in the test env after pytest. Its `GITHUB_TOKEN` is read-only. |

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

## `docs-check.yml`

Keeps a package's published docs (`README.md` and `docs/**/*.md`, the files PyPI and the demo UIs
import) correct and clean at every commit. It runs two jobs:

- **`cli-reference`** regenerates the Typer CLI reference with
  `python -m typer <cli-module> utils docs --name <cli-name> --output <cli-output>`. It fails if the
  committed file differs or is missing. It is skipped when `cli-module` is empty, for a package with no CLI.
  It installs the package from the repo's `uv.lock` (`uv sync --frozen`, extras only) when there is one, so the reference
  is rendered by the locked Typer, the same one that generated the committed file. Without a lock it falls
  back to `uv pip install -e .`, which takes the newest Typer.
- **`hygiene`** fails on:
  - RFC 1918 and link-local IPv4 addresses;
  - `/home/<user>`, `/Users/<user>` and `/srv/...` paths;
  - email addresses, except noreply addresses, `git@` remotes and `example.com/org/net`;
  - any term on the optional `denylist` secret.

  Placeholders such as `<GPU_HOST>` or `/home/<user>` pass. Denylist terms are masked in the log, so a
  hit never prints the term.

Add `.github/workflows/docs.yml`. The UIs import at `dev` HEAD, so run it on every push to `dev` as
well as on tags:

```yaml
name: Docs
on:
  push:
    branches: [dev, main]
    tags: ["v*"]
  pull_request:
    branches: [dev, main]

jobs:
  docs:
    uses: smk762/argus-ci/.github/workflows/docs-check.yml@v1
    with:
      cli-module: argus_curator.cli   # omit for a package without a CLI
      cli-name: argus-curator
      install-extras: cli             # whatever the CLI needs to import
    secrets:
      denylist: ${{ secrets.DOCS_DENYLIST }}   # optional
```

To regenerate the reference locally, run `uv run python -m typer argus_curator.cli utils docs --name argus-curator --output docs/cli.md`.

| Input            | Default       | Notes                                                                      |
| ---------------- | ------------- | -------------------------------------------------------------------------- |
| `cli-module`     | `""`          | Module holding the Typer app; empty skips `cli-reference`.                 |
| `cli-name`       | `""`          | Command name shown in the reference. Required with `cli-module`.           |
| `cli-output`     | `docs/cli.md` | Committed path of the reference.                                           |
| `install-extras` | `""`          | Extras needed to import the CLI, e.g. `cli`.                               |
| `python-version` | `3.12`        | Python used to import the CLI.                                             |
| `allow-pattern`  | `""`          | Regex. A finding on a line matching it is ignored (for false positives).   |

Secret: `denylist` (optional). It holds newline-separated private terms, matched case-insensitively. It is
never committed. A secret is not passed to pull requests from forks, so the denylist is skipped there.

## `bombadil.yml`

Property-based UI testing with [Bombadil](https://github.com/antithesishq/bombadil) against a
static build of a demo UI, lifted from argus-studio's PR job (argus-studio#240/#241). It builds the
UI, serves the build on `127.0.0.1:4173` and lets Bombadil drive a browser around it at random
(clicks, typing, scrolling, back/reload) for `time-limit`, checking the UI's spec in every state.
On a violation it uploads the `bombadil-output` trace and writes the replay commands to the job
summary.

The build is served the way a `trailingSlash` export and Cloudflare Pages resolve routes: `/x/` →
`x/index.html`, and `/x` → `x`, `x/index.html` or `x.html`. Anything else is a 404, so a missing
asset fails `noHttpErrorCodes`.

**Only point it at a static or mock-backed build.** Random clicks press any delete, purge or move
button a live backend offers. The UI needs a backend-free build command, a spec, and
`@antithesishq/bombadil` as a devDependency at `bombadil-version` (the spec imports it).

```yaml
jobs:
  bombadil:
    uses: smk762/argus-ci/.github/workflows/bombadil.yml@v1
    with:
      working-directory: web
```

| Input               | Default                | Notes                                                                           |
| ------------------- | ---------------------- | ------------------------------------------------------------------------------- |
| `working-directory` | `.`                    | Directory holding the UI's `package.json`.                                      |
| `node-version`      | `22`                   | Node for `npm ci` and the build.                                                |
| `build-command`     | `npm run build:static` | Builds the static UI into `serve-dir`.                                          |
| `serve-dir`         | `out`                  | Build output, relative to `working-directory`.                                  |
| `specification`     | `bombadil/spec.ts`     | Bombadil spec, relative to `working-directory`.                                 |
| `time-limit`        | `3m`                   | How long Bombadil explores. Keep it well under `timeout-minutes`.               |
| `bombadil-version`  | `0.7.10`               | Version the action runs; match the devDependency.                               |
| `exit-on-violation` | `true`                 | Stop at the first violation (a PR gate); `false` keeps exploring (a long run).  |
| `continue-on-error` | `false`                | Report a violation (summary, trace, `violations` output) with the job still green, while a new spec beds in. |
| `timeout-minutes`   | `20`                   | Job timeout.                                                                    |

Output: `violations`, the space-separated names of the violated properties (empty when none).
`bombadil-self-test.yml` runs it on `bombadil-fixture/`: the clean build must pass, and a build that
logs a console error must report `noConsoleErrors`.

## `suite-rules.yml`

Lint rules that each eliminate a class of mistake found across the suite (missing timeouts,
request input reaching the filesystem or an outbound URL, secrets compared with `==`…). The
catalogue is [`suite-rules/catalogue.toml`](suite-rules/catalogue.toml): every rule names its
finding class and has a positive and a negative fixture, and
`suite-rules-self-test.yml` proves each one fires on the first and stays silent on the second.
ai-code-auditor scans with the same catalogue, so its findings and CI agree.

It's opt-in. Existing violations are recorded in the repo's `.suite-rules-baseline.json`: CI fails
on **new** violations only, and on a pull request the baseline may only shrink compared with the base
branch: no rule's total may grow, so a renamed file or an edited line only needs the baseline regenerated.

```yaml
jobs:
  suite-rules:
    uses: smk762/argus-ci/.github/workflows/suite-rules.yml@v1
```

To adopt it, write the baseline from an argus-ci checkout and commit it with the job:

```bash
RUFF="uvx ruff@0.15.16" SEMGREP="uvx --from semgrep==1.180.0 semgrep" \
  python3 suite-rules/check.py baseline --root ../argus-<repo>
```

To silence one hit for a reason, add `# noqa: <code>` (ruff rules) or `# nosemgrep: <rule-id>`
on that line, with the reason in the comment. When you fix baselined hits, run `baseline` again so
the file shrinks.

When the catalogue gains a rule, a repo with existing hits regenerates its baseline in a pull request.
The baseline records the rules it was written with, so a rule the base branch's baseline has never
seen may enter with its hits once. After that it only shrinks, like the rest.

### The service directory rules

Two conventions keep the suite's service directory complete (argus-cortex#212). They run in every
repo that calls the workflow, whatever its kind: a UI or stack repo's compose file runs services too.

- **`service-peer-label`**: every service in a compose file (`*compose*.yaml` / `.yml`) carries an
  `argus.peer` label, the name argus-iris's directory lists it under. The label may be a mapping or
  a `key=value` list, on the service or in an anchor it merges (`<<: *service`). A repo with no
  compose file has nothing to check.
  - The rule doesn't guess which containers are peers. One that isn't (a third-party image, a
    one-shot CLI or test container, a trainer, a Wyoming bridge, a web UI) says so on its own line:

    ```yaml
    services:
      kubo:  # nosemgrep: service-peer-label  third-party image (IPFS)
        image: ipfs/kubo:v0.43.1
    ```

  - An overlay file is read with the files beside it. An entry in `compose.build.yaml` for a
    service that `compose.yaml` in the same directory labels is that same container and passes. An
    entry with no `image`, `build` or merged anchor only adjusts a service and isn't checked.
- **`handrolled-health`**: a Starlette or FastAPI app serves `/health` through
  `argus_cortex.service.install_health`, not a route of its own (`@app.get("/health")`,
  `add_api_route`, `add_route`, `Route("/health", ...)`). A guard in front of the app that answers
  its own body for `/health`, as argus-echo's does, registers no route and passes. Calling a peer's
  `/health` is not a route either.

The rule can't tell that an app serves no `/health` at all, or that `argus.peer` names the right
peer. `argus.port` on a container that publishes several ports isn't checked.

| Input | Default | Meaning |
|---|---|---|
| `rules-ref` | `v1` | argus-ci ref the catalogue is read from. Keep it in step with the `@ref` you call. |
| `paths` | `.` | Space-separated paths to scan. |

Tool versions are pinned in the catalogue (`[tools]`). *Convention* rules enforce a code shape; the
auditor doesn't count their hits as findings:

- `silent-except`: a deliberate swallow must say so (`contextlib.suppress(...)` with a comment), so
  the real silent failures stand out.
- `sibling-checkout-read`: no path into a sibling repo's checkout (`../argus-x`, `/home/<user>/argus-x`,
  `.parent / "argus-x"`). Repos talk over HTTP or a versioned schema (SUITE.md's shared rules).
- `cortex-copy`: no local copy of a helper cortex ships (`safe_join`, `safe_name`, `env_flag`,
  `WriteGuard`, `DEFAULT_EXPOSED_LABELS`). Import it from `argus_cortex`.


### Test prompts

The same job holds every prompt a repo's tests send to a reviewed allowlist, so no sexual, violent
or illegal text is committed as a test prompt. `check.py prompts` collects the strings given to a
`prompt`, `user_prompt`, `negative_prompt`, `negative` (or `*_prompt`) keyword, dict key or variable
in test files, and the same keys in `*.jsonl` under `tests/` or `eval/`. Each one must be a line of
the repo's `.suite-prompts-allowlist.txt`, so a new prompt shows up in review as its own line.

It's opt-in: the step runs once the allowlist exists. To adopt, review the prompts it finds and commit
the file:

```sh
python3 suite-rules/check.py prompts --root ../argus-<repo> --write
```

Pass extra paths to scan in full, test or not (`check.py prompts --root . demo/`).
## Why release/publish is **not** here

PyPI [trusted publishing cannot run inside a reusable workflow](https://docs.pypi.org/trusted-publishers/troubleshooting/#reusable-workflows-on-github)
(the OIDC `job_workflow_ref` check rejects it). So each repo keeps a **top-level**
`release.yml`. Its canonical form lives in
[`argus-pkg-template`](https://github.com/smk762/argus-pkg-template); run
`copier update` in a repo to re-sync it.

## Versioning

Callers pin a major tag (`@v1`). Breaking changes to inputs get a new major tag;
`v1` is kept moving to the latest backward-compatible commit.
