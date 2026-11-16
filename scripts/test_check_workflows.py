"""Unit tests for the workflow checks (stdlib unittest)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_workflows import _call, compare, hygiene  # noqa: E402

import yaml  # noqa: E402

OLD = {"inputs": {"a": {"type": "string", "default": "x"}, "b": {"type": "boolean", "default": False}},
       "secrets": {"s": {"required": False}}}


def errs(new):
    return compare("w.yml", OLD, new)[0]


class Compat(unittest.TestCase):
    def test_unchanged_and_additive_pass(self):
        self.assertEqual(errs(OLD), [])
        added = {**OLD, "inputs": {**OLD["inputs"], "c": {"type": "string", "default": ""}}}
        self.assertEqual(errs(added), [])

    def test_removed_input_or_secret_fails(self):
        self.assertTrue(errs({"inputs": {"a": OLD["inputs"]["a"]}, "secrets": OLD["secrets"]}))
        self.assertTrue(errs({"inputs": OLD["inputs"]}))

    def test_type_change_fails(self):
        self.assertTrue(errs({**OLD, "inputs": {**OLD["inputs"], "b": {"type": "string", "default": ""}}}))

    def test_becoming_required_fails(self):
        self.assertTrue(errs({**OLD, "secrets": {"s": {"required": True}}}))
        self.assertTrue(errs({**OLD, "inputs": {**OLD["inputs"], "n": {"type": "string", "required": True}}}))

    def test_default_change_only_warns(self):
        new = {**OLD, "inputs": {**OLD["inputs"], "a": {"type": "string", "default": "y"}}}
        e, w = compare("w.yml", OLD, new)
        self.assertEqual(e, [])
        self.assertEqual(len(w), 1)

    def test_bare_on_key_is_read(self):
        self.assertEqual(_call(yaml.safe_load("on:\n  workflow_call:\n    inputs: {}\n")), {"inputs": {}})
        self.assertIsNone(_call(yaml.safe_load("on: [push]\n")))


class Hygiene(unittest.TestCase):
    def test_permissions_required_and_pull_request_target_refused(self):
        self.assertEqual(hygiene("w", yaml.safe_load("on: [push]\npermissions:\n  contents: read\n")), [])
        self.assertEqual(len(hygiene("w", yaml.safe_load("on: [push]\n"))), 1)
        self.assertEqual(len(hygiene("w", yaml.safe_load("on:\n  pull_request_target:\npermissions: {}\n"))), 1)


if __name__ == "__main__":
    unittest.main()
