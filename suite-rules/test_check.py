"""Unit tests for the baseline and ratchet (stdlib unittest; the fixtures prove the rules)."""
import io
import json
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
        self.assertEqual(check.compare([], mine, base)["grew"], [hit(text="z").key])
        self.assertEqual(check.compare([], Counter({hit().key: 1}), base)["grew"], [])  # shrinking is fine
        self.assertEqual(check.compare([], mine, None)["grew"], [])  # no base: first adoption

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


if __name__ == "__main__":
    unittest.main()
