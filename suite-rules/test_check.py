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

    def test_baseline_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "b.json"
            n = check.write_baseline(p, [hit(), hit(line=5), hit(rule="q", text="a | b")], {"ruff": "1"})
            self.assertEqual(n, 3)
            self.assertEqual(check.read_baseline(p), Counter({hit().key: 2, hit(rule="q", text="a | b").key: 1}))
            self.assertEqual(json.loads(p.read_text())["tools"], {"ruff": "1"})
        self.assertEqual(check.read_baseline(Path("/nonexistent")), Counter())


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

    def test_rejecting_guard_dominates(self):
        # `if flag and bad(x)` and `if not bad(x)` must not match the rejecting-guard sanitizer.
        san = _generate.SANITIZERS
        self.assertNotIn("if <... not $X.resolve(...).is_relative_to(...) ...>:", san)
        self.assertNotIn("if <... $X not in $C ...>:", san)
        self.assertIn("if not $X.resolve(...).is_relative_to(...):", san)
        self.assertIn("if not $X.resolve(...).is_relative_to(...) or ...:", san)
        self.assertIn("if ... or not $X.resolve(...).is_relative_to(...):", san)
        self.assertIn("if $X not in $C:", san)

    def test_request_url_is_the_second_positional(self):
        calls = _generate._url_calls("$U")
        for pattern in ("requests.request($METHOD, $U, ...)", "httpx.request($METHOD, $U, ...)",
                        "$C.request($METHOD, $U, ...)"):
            self.assertIn(pattern, calls, pattern)
        self.assertIn("pattern-not: requests.request($ANY, ...)", calls)
        self.assertIn("pattern-not: httpx.request($ANY, ...)", calls)
        self.assertIn("pattern-not: $C.request($ANY, ...)", calls)

    def test_urlopen_accepts_the_url_keyword(self):
        calls = _generate._url_calls("$U")
        self.assertIn("urllib.request.urlopen(url=$U, ...)", calls)
        self.assertIn("urlopen(url=$U, ...)", calls)
        self.assertIn("requests.$M(url=$U, ...)", calls)

    def test_unpinned_url_prefix_stays_a_sink(self):
        sinks = _generate.URL_SINKS
        self.assertIn(_generate._FSTRING_IN_AUTHORITY, sinks)
        self.assertIn(_generate._FORMAT_SINK, sinks)
        self.assertIn(_generate._LITERAL_OPEN_AUTHORITY, sinks)
        self.assertIn("- pattern: $NAME + $R", sinks)
        # Open authority: scheme://host then the closing quote, with no slash between them.
        self.assertIn("://[^/{}\"']*[\"']$", _generate._LITERAL_OPEN_AUTHORITY)
        self.assertIn("://[^/{}\"']*\\{", _generate._FSTRING_IN_AUTHORITY)
        self.assertIn("://[^/{}\"']*\\{", _generate._FORMAT_SINK)

    def test_basename_and_path_name_keep_taint(self):
        text = _generate.rule("r", "path_traversal", "m", _generate.PATH_SINKS)
        for gone in ("pattern: os.path.basename(...)", "pattern: Path(...).name", "pattern: PurePath(...).name"):
            self.assertNotIn(gone, text, gone)
        for kept in ("os.path.basename($IN)", "Path($IN).name", "PurePath($IN).name", "by-side-effect: false"):
            self.assertIn(kept, text, kept)


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


if __name__ == "__main__":
    unittest.main()
