"""Unit tests for the baseline and ratchet (stdlib unittest; the fixtures prove the rules)."""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check  # noqa: E402


def hit(rule="r", path="a.py", line=1, text="x = 1"):
    return check.Hit(rule, path, line, text)


class Baseline(unittest.TestCase):
    def test_key_ignores_line_numbers(self):
        self.assertEqual(hit(line=3).key, hit(line=90).key)

    def test_new_hits_beyond_the_baseline_fail(self):
        base = Counter({hit().key: 1})
        self.assertEqual(check.compare([hit()], base)["new"], [])
        self.assertEqual(len(check.compare([hit(), hit(line=9)], base)["new"]), 1)  # a second copy is new
        self.assertEqual(len(check.compare([hit(text="y = 2")], base)["new"]), 1)

    def test_fixed_hits_are_reported(self):
        base = Counter({hit().key: 2})
        self.assertEqual(check.compare([hit()], base)["fixed"], 1)

    def test_ratchet_rejects_a_growing_baseline(self):
        mine = Counter({hit().key: 2, hit(text="z").key: 1})
        base = Counter({hit().key: 2})
        self.assertEqual(check.compare([], mine, base)["grew"], [hit().rule])
        self.assertEqual(check.compare([], Counter({hit().key: 1}), base)["grew"], [])  # shrinking is fine
        self.assertEqual(check.compare([], mine, None)["grew"], [])  # no base: first adoption

    def test_ratchet_allows_a_hit_to_move_to_a_new_key(self):
        base = Counter({hit(path="app/api.py").key: 1})
        mine = Counter({hit(path="app/routes.py").key: 1})  # renamed file, same hit
        self.assertEqual(check.compare([hit(path="app/routes.py")], mine, base)["grew"], [])

    def test_a_rule_new_to_the_base_baseline_may_enter_once(self):
        mine = Counter({hit(rule="new-rule").key: 3, hit().key: 1})
        base = Counter({hit().key: 1})
        # The base baseline was written before new-rule existed: its hits may be baselined.
        self.assertEqual(check.compare([], mine, base, frozenset({"r"}))["grew"], [])
        # Once the base baseline knows the rule, it only shrinks.
        self.assertEqual(check.compare([], mine, base, frozenset({"r", "new-rule"}))["grew"], ["new-rule"])
        # A rule the base knows still can't grow alongside a new one.
        grown = Counter({hit(rule="new-rule").key: 3, hit().key: 2})
        self.assertEqual(check.compare([], grown, base, frozenset({"r"}))["grew"], ["r"])

    def test_a_baseline_records_its_rules_and_an_old_one_knows_the_old_catalogue(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "b.json"
            check.write_baseline(p, [hit()], {"ruff": "1"}, ["r", "q"])
            self.assertEqual(check.baseline_rules(p), frozenset({"r", "q"}))
            p.write_text(json.dumps({"version": 1, "tools": {}, "entries": []}))  # written before rules were recorded
            old = check.baseline_rules(p)
            self.assertIn("missing-timeout", old)
            self.assertNotIn("service-peer-label", old)
            self.assertNotIn("handrolled-health", old)
            self.assertIsNone(check.baseline_rules(Path(d) / "missing.json"))

    def test_check_lets_a_new_rule_into_the_baseline_and_then_ratchets_it(self):
        entry = {"rule": "service-peer-label", "path": "compose.yaml", "text": "db:", "count": 1}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            (root / check.BASELINE).write_text(json.dumps({"version": 1, "tools": {}, "entries": [entry]}))
            old_base, new_base = Path(d) / "old.json", Path(d) / "new.json"
            old_base.write_text(json.dumps({"version": 1, "tools": {}, "entries": []}))
            new_base.write_text(json.dumps({"version": 1, "tools": {}, "rules": ["service-peer-label"], "entries": []}))
            out = io.StringIO()
            with mock.patch.object(check, "scan", lambda *a, **kw: []), redirect_stdout(out):
                self.assertEqual(check.main(["check", "--root", str(root), "--base-baseline", str(old_base)]), 0)
                self.assertEqual(check.main(["check", "--root", str(root), "--base-baseline", str(new_base)]), 1)
            self.assertIn("service-peer-label", out.getvalue())

    def test_baseline_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "b.json"
            n = check.write_baseline(p, [hit(), hit(line=5), hit(rule="q", text="a | b")], {"ruff": "1"})
            self.assertEqual(n, 3)
            self.assertEqual(check.read_baseline(p), Counter({hit().key: 2, hit(rule="q", text="a | b").key: 1}))
            self.assertEqual(json.loads(p.read_text())["tools"], {"ruff": "1"})
        self.assertEqual(check.read_baseline(Path("/nonexistent")), Counter())


class SemgrepRun(unittest.TestCase):
    """A semgrep that crashed must fail the check, never read as a clean run."""

    def _run(self, code):
        rule = next(r for r in check.load_rules()[0] if r.tool == "semgrep")
        fake = f"{sys.executable} -c {code!r}"
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"SEMGREP": fake}):
            Path(d, "a.py").write_text("x = 1\n")
            return check.run_semgrep([rule], Path(d), [])

    def test_a_crash_with_exit_1_and_no_report_fails(self):
        # what semgrep did with an unwritable HOME: a traceback on stderr, exit 1, nothing on stdout
        with self.assertRaisesRegex(RuntimeError, "semgrep failed"):
            self._run("import sys; sys.stderr.write('PermissionError'); sys.exit(1)")

    def test_a_report_with_no_results_is_a_clean_run(self):
        self.assertEqual(self._run("import json; print(json.dumps({'results': [], 'errors': []}))"), [])


class Prompts(unittest.TestCase):
    def test_prompt_named_values_are_collected(self):
        src = (
            'run(user_prompt="a cat", negative_prompt="blurry", prompt_id="not-a-prompt")\n'
            'body = {"prompt": f"a {role}  on\\n a rug", "negative": ""}\n'
            'prompts = ["x", ("y",)]\n'
            'expanded_prompt: str = "z"\n'
            'other = "not collected"\n'
        )
        self.assertEqual(sorted(check.prompts_in_py(src)), ["a cat", "a {} on a rug", "blurry", "x", "y", "z"])

    def test_jsonl_skips_comments_and_reads_prompt_keys(self):
        text = '// header\n{"prompt": "a lake", "negative": "blurry", "group": "safe"}\nnot json\n'
        self.assertEqual(check.prompts_in_jsonl(text), ["a lake", "blurry"])

    def test_only_tests_and_eval_are_scanned_unless_listed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel, text in {
                "tests/test_a.py": 'run(prompt="in a test")',
                "src/pkg/app.py": 'run(prompt="in the app")',
                "demo/markers.py": 'run(prompt="a demo marker")',
                "eval/probes.jsonl": '{"prompt": "a probe"}',
                ".venv/lib/test_x.py": 'run(prompt="vendored")',
            }.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text)
            self.assertEqual(sorted(check.collect_prompts(root)), ["a probe", "in a test"])
            self.assertIn("a demo marker", check.collect_prompts(root, ["demo"]))

    def test_an_unlisted_prompt_fails_until_allowlisted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "tests").mkdir()
            (root / "tests" / "test_a.py").write_text('run(prompt="a cat")')
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(check.main(["prompts", "--root", d]), 1)
                self.assertEqual(check.main(["prompts", "--root", d, "--write"]), 0)
                self.assertEqual(check.main(["prompts", "--root", d]), 0)
                (root / "tests" / "test_a.py").write_text('run(prompt="a cat")\nrun(prompt="a dog")')
                self.assertEqual(check.main(["prompts", "--root", d]), 1)
            self.assertIn("'a dog'", out.getvalue())
            self.assertEqual(check.read_allowlist(root / check.PROMPT_ALLOWLIST), {"a cat"})

    def test_a_prompt_starting_with_a_hash_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "tests").mkdir()
            (root / "tests" / "test_a.py").write_text('run(prompt="# Summarise this")\nrun(prompt="\\\\x")')
            with redirect_stdout(io.StringIO()):
                self.assertEqual(check.main(["prompts", "--root", d, "--write"]), 0)
                self.assertEqual(check.main(["prompts", "--root", d]), 0)
            self.assertEqual(check.read_allowlist(root / check.PROMPT_ALLOWLIST), {"# Summarise this", "\\x"})


class Catalogue(unittest.TestCase):
    def test_catalogue_loads_and_every_rule_has_fixtures(self):
        rules, tools = check.load_rules()
        self.assertIn("ruff", tools)
        self.assertIn("semgrep", tools)
        for r in rules:
            d = check.HERE / "fixtures" / r.id
            self.assertTrue(check._fixture_files(d, "positive"), r.id)
            self.assertTrue(check._fixture_files(d, "negative"), r.id)

    def test_bad_catalogue_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('[[rules]]\nid = "a"\nclass = "c"\ntool = "ruff"\nmessage = "m"\n')
            with self.assertRaises(ValueError):
                check.load_rules(p)  # a ruff rule without codes
            p.write_text('[[rules]]\nid = "a"\nclass = "c"\ntool = "ruff"\ncodes = ["S1"]\nkind = "vibes"\nmessage = "m"\n')
            with self.assertRaises(ValueError):
                check.load_rules(p)


class Fixtures(unittest.TestCase):
    """fixtures() with scanning stubbed: `fires` is the set of file names the fake rule hits."""

    def run_fixtures(self, files: dict[str, str], fires: set[str]) -> dict:
        rule = check.Rule("r", "c", "semgrep", "LOW", "m")
        with tempfile.TemporaryDirectory() as d:
            fx = Path(d) / "fixtures" / "r"
            fx.mkdir(parents=True)
            for name, text in files.items():
                (fx / name).write_text(text)

            def fake_scan(root, paths, **kw):
                return [check.Hit("r", p, 1, "x") for p in paths if p in fires]

            with mock.patch.object(check, "HERE", Path(d)), mock.patch.object(check, "scan", fake_scan):
                return check.fixtures([rule])[0]

    def test_non_python_fixtures_are_found(self):
        res = self.run_fixtures({"positive.yml": "a", "negative.yml": "b"}, {"positive.yml"})
        self.assertTrue(res["ok"], res)

    def test_every_positive_file_must_fire(self):
        files = {"positive.py": "a", "positive_2.py": "a", "negative.py": "b"}
        res = self.run_fixtures(files, {"positive.py"})
        self.assertFalse(res["ok"])
        self.assertIn("positive_2.py", res["note"])
        self.assertTrue(self.run_fixtures(files, {"positive.py", "positive_2.py"})["ok"])


sys.path.insert(0, str(check.HERE / "semgrep"))
import _generate  # noqa: E402


class Generate(unittest.TestCase):
    def test_message_and_class_cannot_break_the_yaml(self):
        msg, cls = "line one: x\n  - id: zz-smuggled\n# not a comment", "[a]: b # c"
        lines = _generate.rule("r", cls, msg, "").splitlines()
        message = next(ln for ln in lines if ln.startswith("    message:"))
        klass = next(ln for ln in lines if ln.startswith("      class:"))
        self.assertEqual(json.loads(message.split(":", 1)[1]), msg)
        self.assertEqual(json.loads(klass.split(":", 1)[1]), cls)
        self.assertFalse(any("zz-smuggled" in ln for ln in lines if ln is not message))

    def test_starlette_request_sources(self):
        src = _generate.sources()
        for p in ("request.headers", "request.cookies", "request.url", "await request.body()", "request.stream()"):
            self.assertIn(f"- pattern: {p}\n", src + "\n", p)

    def test_validator_names_are_anchored(self):
        import re
        raising, predicate = re.compile(_generate.RAISING_VALIDATOR), re.compile(_generate.PREDICATE)
        for name in ("re.match", "fnmatch", "log_check", "shallow_copy", "checksum", "subprocess.check_output",
                     "require", "ensure_dir", "safely_log"):
            self.assertFalse(raising.match(name) or predicate.match(name), name)
        for name in ("validate_name", "argus_cortex.fs.safe_join", "safe_name", "get_or_404", "ensure_within_root"):
            self.assertTrue(raising.match(name), name)
        for name in ("is_safe_name", "allowed_file", "host_is_allowed", "is_within_root"):
            self.assertTrue(predicate.match(name), name)

    def test_no_sanitizer_clears_a_value_without_a_check(self):
        san = _generate.SANITIZERS
        # A bare resolve(), an unguarded membership test or a bare commonpath() checks nothing.
        for gone in ("- pattern: $X.resolve(...)\n", "- pattern: $X in $C\n", "- pattern: $X not in $C\n",
                     "- pattern: os.path.commonpath([..., $X, ...])\n", "if <... $X.resolve() ...>:"):
            self.assertNotIn(gone, san + "\n", gone)
        # Every guard that is not a raising call has to reject: no `if X in C: pass`-style sanitizer.
        self.assertEqual(san.count("by-side-effect: true"), 2)

    def test_url_templates_are_sinks_at_their_leading_part(self):
        sinks = _generate.URL_SINKS
        self.assertIn('- pattern: f"{$U}..."', sinks)
        self.assertIn("- pattern: $U + $R", sinks)
        self.assertNotIn('pattern-not: $X.$M("..." + $Y, ...)', sinks)

    def test_rejecting_guard_requires_the_check_to_dominate(self):
        # `<... c ...>` matches an `and` operand and a negated test, so neither can be a guard.
        self.assertNotIn("<...", _generate.SANITIZERS)
        guard = _generate._guard(["$X not in $C"], "c")
        self.assertIn("if $X not in $C:\n", guard)
        self.assertIn("if $X not in $C or ...:\n", guard)
        self.assertIn("if ... or $X not in $C:\n", guard)
        self.assertIn("if ... or $X not in $C or ...:\n", guard)

    def test_request_method_takes_the_url_second(self):
        sinks = _generate.URL_SINKS
        for pat in ("requests.request($METHOD, $U, ...)", "httpx.request($METHOD, $U, ...)",
                    "$C.request($METHOD, $U, ...)"):
            self.assertIn(pat, sinks, pat)
        # The first-positional method list must not include request(), or the method string is the sink.
        self.assertNotIn("|request|", sinks)

    def test_urlopen_keyword_is_a_sink(self):
        sinks = _generate.URL_SINKS
        self.assertIn("urllib.request.urlopen(url=$U, ...)", sinks)
        self.assertIn("\n              - pattern: urlopen(url=$U, ...)\n", sinks)

    def test_unpinned_host_template_stays_a_sink(self):
        sinks = _generate.URL_SINKS
        # A constant prefix is a sink-exclusion only when it is scheme, host and a slash.
        # `BASE + user` is `$L + $U`; an f-string hole in the authority is a pattern-regex.
        self.assertIn("$L + $U", sinks)
        self.assertIn('pattern-regex: "://', sinks)
        self.assertIn("[a-zA-Z][a-zA-Z0-9+.-]*://", sinks)

    def test_basename_and_path_name_are_not_sanitizers(self):
        san = _generate.SANITIZERS
        for gone in ("os.path.basename(...)", "Path(...).name", "PurePath(...).name"):
            self.assertNotIn(f"- pattern: {gone}", san, gone)
        # Dropping the sanitizer is not enough: taint_assume_safe_functions would still drop the
        # call. The argument's taint has to reach the result.
        text = _generate.rule("r", "c", "m", "")
        self.assertIn("^(.*\\.)?basename$", text)
        self.assertIn("^(.*\\.)?(Pure)?Path$", text)
        self.assertIn("by-side-effect: false", text)


def _semgrep_available() -> bool:
    import shutil
    return bool(os.environ.get("SEMGREP")) or shutil.which("semgrep") is not None


@unittest.skipUnless(_semgrep_available(), "needs semgrep ($SEMGREP or on PATH); CI sets $SEMGREP")
class TaintFixtures(unittest.TestCase):
    """The taint rules against their fixtures: each positive file is one bypass the sanitizers must not clear."""

    def test_taint_rules_hold_on_their_fixtures(self):
        rules = [r for r in check.load_rules()[0] if r.id in ("request-path-to-fs", "request-url-outbound")]
        self.assertEqual(len(rules), 2)
        for res in check.fixtures(rules):
            self.assertTrue(res["ok"], f"{res['rule']}: {res['note']}")


LABELLED = """services:
  argus-widget:
    build: .
    ports: ["8199:8199"]
    labels:
      argus.peer: widget
      argus.service: argus-widget
      argus.health: /health
      argus.port: "8199"
"""
INSTALLED = """from argus_cortex.service import install_health
from fastapi import FastAPI

app = FastAPI()
install_health(app, service="argus-widget")
"""


@unittest.skipUnless(_semgrep_available(), "needs semgrep ($SEMGREP or on PATH); CI sets $SEMGREP")
class ServiceDirectory(unittest.TestCase):
    """service-peer-label and handrolled-health against small repos (argus-cortex#212)."""

    def hits(self, files: dict[str, str]) -> list[tuple[str, str, str]]:
        rules = [r for r in check.load_rules()[0] if r.id in (check.PEER_LABEL, "handrolled-health")]
        self.assertEqual(len(rules), 2)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text)
            return [(h.rule, h.path, h.text) for h in check.scan(root, rules=rules)]

    def test_a_labelled_service_with_install_health_passes(self):
        self.assertEqual(self.hits({"compose.yaml": LABELLED, "src/argus_widget/server.py": INSTALLED}), [])

    def test_a_repo_with_no_compose_file_has_nothing_to_label(self):
        self.assertEqual(self.hits({"src/argus_widget/server.py": INSTALLED}), [])

    def test_an_unlabelled_service_container_fails(self):
        compose = LABELLED.replace("      argus.peer: widget\n", "")
        self.assertEqual(self.hits({"docker-compose.yaml": compose}),
                         [(check.PEER_LABEL, "docker-compose.yaml", "argus-widget:")])

    def test_an_allowlisted_container_passes_and_a_plain_comment_does_not(self):
        compose = LABELLED + (
            "  postgres:  # nosemgrep: service-peer-label  third-party image\n"
            "    image: postgres:17\n"
            "  trainer:  # nosemgrep: service-peer-label  one-shot trainer, serves nothing\n"
            "    build: .\n"
            "    profiles: [train]\n"
            "  ollama:  # third-party\n"
            "    image: ollama/ollama:0.12.0\n")
        self.assertEqual(self.hits({"compose.yaml": compose}),
                         [(check.PEER_LABEL, "compose.yaml", "ollama: # third-party")])

    def test_a_baselined_container_passes_check(self):
        compose = LABELLED + "  kubo:\n    image: ipfs/kubo:v0.43.1\n"
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "compose.yaml").write_text(compose)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(check.main(["check", "--root", d]), 1)
                self.assertEqual(check.main(["baseline", "--root", d]), 0)
                self.assertEqual(check.main(["check", "--root", d]), 0)
            written = json.loads((Path(d) / check.BASELINE).read_text())
            self.assertEqual([e["text"] for e in written["entries"]], ["kubo:"])
            self.assertIn(check.PEER_LABEL, written["rules"])

    def test_an_overlay_entry_is_the_service_its_base_file_labels(self):
        overlay = "services:\n  argus-widget:\n    build:\n      context: ../argus-widget\n"
        self.assertEqual(self.hits({"compose.yaml": LABELLED, "compose.build.yaml": overlay}), [])
        # Without a labelled base beside it, or with the base in another directory, it is an unlabelled service.
        want = [(check.PEER_LABEL, "compose.build.yaml", "argus-widget:")]
        self.assertEqual(self.hits({"compose.build.yaml": overlay}), want)
        self.assertEqual(self.hits({"stack/compose.yaml": LABELLED, "compose.build.yaml": overlay}), want)

    def test_other_yaml_with_a_services_key_is_not_a_compose_file(self):
        workflow = "jobs:\n  test:\n    services:\n      postgres:\n        image: postgres:17\n"
        self.assertEqual(self.hits({".github/workflows/ci.yml": workflow, "config.yaml": LABELLED.replace(
            "      argus.peer: widget\n", "")}), [])

    def test_a_hand_rolled_health_route_fails(self):
        app = ("from fastapi import FastAPI\n\napp = FastAPI()\n\n\n"
               '@app.get("/health")\ndef health():\n    return {"status": "ok"}\n')
        self.assertEqual(self.hits({"src/argus_widget/server.py": app}),
                         [("handrolled-health", "src/argus_widget/server.py", '@app.get("/health")')])

    def test_install_health_behind_an_asgi_guard_passes(self):
        # argus-echo's shape: a guard in front of the app answers its own 503 body; install_health serves the route.
        guard = INSTALLED + (
            "\n\nclass Guard:\n"
            "    def __init__(self, inner):\n        self.inner = inner\n\n"
            "    async def __call__(self, scope, receive, send):\n"
            '        if scope["type"] == "http" and scope["method"] == "GET" and scope["path"] == "/health":\n'
            "            pass\n"
            "        await self.inner(scope, receive, send)\n")
        self.assertEqual(self.hits({"engines/widget/server.py": guard}), [])


if __name__ == "__main__":
    unittest.main()
