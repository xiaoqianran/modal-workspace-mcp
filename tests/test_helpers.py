import unittest

from modal_workspace_mcp.helpers import (
    bounded_int,
    require_allowlisted,
    require_bearer_token,
    truncate_text,
    validate_packages,
    validate_sandbox_name,
)


class HelpersTest(unittest.TestCase):
    def test_bearer(self):
        self.assertTrue(require_bearer_token("Bearer abc", "abc"))
        self.assertFalse(require_bearer_token("Bearer nope", "abc"))
        self.assertFalse(require_bearer_token(None, "abc"))

    def test_sandbox_name(self):
        self.assertEqual(validate_sandbox_name("repo-build_1"), "repo-build_1")
        with self.assertRaises(ValueError):
            validate_sandbox_name("bad name")

    def test_packages(self):
        self.assertEqual(validate_packages(["git", "torch==2.8.0"], field="x"), ["git", "torch==2.8.0"])
        with self.assertRaises(ValueError):
            validate_packages(["bad package;rm -rf /"], field="x")

    def test_allowlist(self):
        self.assertEqual(require_allowlisted(["hf"], {"hf"}, kind="secret"), ["hf"])
        with self.assertRaises(ValueError):
            require_allowlisted(["root"], {"hf"}, kind="secret")

    def test_bounds_and_truncation(self):
        self.assertEqual(bounded_int(3, minimum=1, maximum=5, field="n"), 3)
        with self.assertRaises(ValueError):
            bounded_int(6, minimum=1, maximum=5, field="n")
        text, truncated = truncate_text("abcdef", 3)
        self.assertTrue(truncated)
        self.assertTrue(text.startswith("abc"))


if __name__ == "__main__":
    unittest.main()
