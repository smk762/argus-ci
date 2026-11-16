"""Unit tests for the baseline and ratchet (stdlib unittest; the fixtures prove the rules)."""
import json
import sys
import tempfile
import unittest
from collections import Counter
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


class Catalogue(unittest.TestCase):
    def test_catalogue_loads_and_every_rule_has_fixtures(self):
        rules, tools = check.load_rules()
        self.assertIn("ruff", tools)
        self.assertIn("semgrep", tools)
        for r in rules:
            d = check.HERE / "fixtures" / r.id
            self.assertTrue(list(d.glob("positive*.py")), r.id)
            self.assertTrue(list(d.glob("negative*.py")), r.id)

    def test_bad_catalogue_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('[[rules]]\nid = "a"\nclass = "c"\ntool = "ruff"\nmessage = "m"\n')
            with self.assertRaises(ValueError):
                check.load_rules(p)  # a ruff rule without codes
            p.write_text('[[rules]]\nid = "a"\nclass = "c"\ntool = "ruff"\ncodes = ["S1"]\nkind = "vibes"\nmessage = "m"\n')
            with self.assertRaises(ValueError):
                check.load_rules(p)


if __name__ == "__main__":
    unittest.main()
