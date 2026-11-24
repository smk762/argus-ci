# CLAUDE.md — argus-ci

Guidance for AI agents working in this repo. Human-facing usage, including the inputs table for each workflow, lives
in [README.md](README.md).

## What this is

**Not a package.** There is no `src/` and no `pyproject.toml`. This repo holds the Argus suite's **reusable GitHub
Actions workflows**, plus the **suite-rules** lint catalogue. Editing a file here changes CI for **every consumer at
once**. The `workflow_call` inputs and secrets are a public API, and consumers pin a major tag (`@v1`).

## Argus suite
<!-- argus-suite: keep this block; argus-ci checks for it -->
This repo is part of the Argus suite. The suite map below lists every sibling and what it owns; check it before
building something a sibling may already do. **On every release, update this repo's row and capabilities in
argus-cortex's SUITE.md** (a PR to argus-cortex in the same release).

@../argus-core/SUITE.md

Not checked out? Read https://github.com/smk762/argus-cortex/blob/dev/SUITE.md

## Must never happen

Each row names what enforces it. An **UNENFORCED** row is a known gap: when one bites, add a check, not more prose.

| Never | Enforced by |
|---|---|
| A reusable workflow loses an input or a secret, changes an input's type, or gains a required one | `self-check.yml` → `scripts/check_workflows.py`, compared with `v1` (`scripts/test_check_workflows.py`) |
| `v1` moved over a breaking change | The same check. `dev` stays `v1`-compatible, and a deliberate break must change `BASE` in `self-check.yml` to the new major in the same PR |
| A workflow with no top-level `permissions:`, or a `pull_request_target` trigger | `scripts/check_workflows.py` (hygiene) |
| A workflow that fails syntax, expression or shellcheck checks | `self-check.yml` → actionlint |
| A suite rule without a positive and a negative fixture, or one that fires on its negative | `suite-rules-self-test.yml` (`check.py fixtures`, `test_check.py`) |
| A consumer's suite-rules baseline that grows, except with the hits of a rule new to it | `check.py check --base-baseline` (`test_check.py::test_ratchet_rejects_a_growing_baseline`, `::test_a_rule_new_to_the_base_baseline_may_enter_once`) |
| Stale generated semgrep rules | `suite-rules-self-test.yml` (`_generate.py` + `git diff --exit-code`) |
| A consumer's CLAUDE.md without the argus-suite block, or a repo with no SUITE.md row | `suite-check.yml` |
| The "Not checked out?" link pointing at `blob/main` | `suite-check.yml`, as a **warning** until the fleet is fixed. Then make it an error |
| Release or publish (PyPI OIDC) inside a reusable workflow | PyPI refuses it (its `job_workflow_ref` check). Each repo keeps a top-level `release.yml` from argus-pkg-template |
| A secret-derived value echoed without `::add-mask::` first | **UNENFORCED** |
| A docs-check hygiene regex widened without running it over the siblings' docs first | **UNENFORCED** (it is a fleet gate: one bad pattern fails every consumer) |
| A third-party action not pinned to a major tag (or to a full commit SHA with a `# vN` comment), or pinned to an older major than the same action elsewhere here | **UNENFORCED** |

## Layout

- `.github/workflows/python-ci.yml`: the reusable Python pipeline (uv, ruff, pytest, build).
- `.github/workflows/suite-check.yml`: the reusable suite-map check.
- `.github/workflows/docs-check.yml`: the reusable docs check (CLI reference drift, published-docs hygiene).
- `.github/workflows/suite-rules.yml`: the reusable suite-rules check.
- `.github/workflows/bombadil.yml`: the reusable Bombadil UI check (static build, served locally). `bombadil-fixture/` + `bombadil-self-test.yml` prove it.
- `suite.yml`, `suite-rules-self-test.yml`, `bombadil-self-test.yml` and `self-check.yml` are this repo's own CI.
- `suite-rules/`: the catalogue (`catalogue.toml`), semgrep rules, fixtures, and `check.py`.
- `scripts/check_workflows.py`: the hygiene and input-compatibility check.

## Suite rules

`suite-rules/catalogue.toml` lists rules. Each rule names the ai-code-auditor finding class it eliminates
(`config/finding_classes.yaml` there), and the auditor runs the same `check.py` nightly, so its findings and CI agree.

- **A new guard rule** needs a fixture pair under `fixtures/<id>/`, and the same class with a `static_rules.suite`
  entry in ai-code-auditor. Land the auditor side first: the auditor doesn't map a rule it hasn't seen, so it sends
  that rule's hits to its model classifier instead. `kind = "convention"` rules enforce a code shape and are not counted as findings.
- **A repo opts in** with `suite-rules.yml`. Existing hits go in its `.suite-rules-baseline.json`, which may only
  shrink. Silence one hit with a reasoned `# noqa: <code>` or `# nosemgrep: <id>` on that line.
- **A new rule's hits may enter a baseline once.** A baseline records the rules it was written with
  (`rules`), and the ratchet skips a rule the base branch's baseline doesn't list. A baseline with no list knows
  `RULES_BEFORE_RECORDING` in `check.py`: never add a rule to that set.
- **Rules are not scoped per repo.** Every rule runs wherever the workflow is called. A rule that only applies to
  some containers or files (`service-peer-label`) says so in its pattern, and a repo exempts the rest in its own
  files, with a reasoned `nosemgrep` or its baseline.
- **`service-peer-label` has a helper rule**, `service-peer-labelled`, in the same semgrep file. `check.py` uses it
  to pass an overlay file's entry for a service that a compose file beside it labels, and never reports it.
- **The tool pins** (ruff, semgrep) live in the catalogue's `[tools]`. CI and the auditor both read them from there.
- **Before adding or widening a rule**, run it over every repo's `origin/dev`, and record the false positives in the PR.

## Releasing

Consumers pin `@v1`. A backward-compatible change fast-forwards the tag: `git tag -f v1 <sha> && git push -f origin v1`.
Moving it is a fleet change, so dry-run it from one consumer's branch first. A breaking change cuts `v2` and leaves
`v1` where it is.

## Gotchas

- `post-test` runs arbitrary caller-supplied shell in the test env. That's by design: keep it opt-in and empty by default.
- `uv run --no-sync` everywhere: the editable install already happened, and `--no-sync` stops uv re-resolving.
- `astral-sh/setup-uv` publishes no floating major tags after `v7`, so moving past `@v7` means a full version pin.
- New secrets must be `required: false` (fork PRs get none) and documented in the README.

## Branches

`dev` is the default branch and the base for every PR. Cut feature branches from `origin/dev` and bring them up to date by merging `origin/dev`, never `main`. Never push work to `main` or open a PR against it, except the release PR from `dev`: `main` must never be ahead of `dev`, with one exception. A release fast-forwards `main` to a `dev` commit that passed CI (`git push origin origin/dev:main`), then tags it. If `main` is protected, the release is a reviewed PR from `dev` into `main`, and merging it leaves a merge commit on `main` alone. That merge commit is the one exception to the rule: it leaves `main` one commit ahead of `dev` with an identical tree. Leave it there and don't merge `main` back into `dev`. Anything else on `main` that `dev` lacks is a mistake (`git diff origin/dev origin/main` must be empty). Once `main` carries such a commit it can't be fast-forwarded, so later releases are PRs too.
