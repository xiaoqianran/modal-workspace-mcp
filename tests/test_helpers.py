import unittest

from modal_workspace_mcp.helpers import (
    bounded_float,
    require_allowlisted,
    require_bearer_token,
    validate_cidrs,
    validate_domains,
    validate_image_id,
    validate_packages,
    validate_remote_path,
    validate_sandbox_name,
)


class HelpersTest(unittest.TestCase):
    def test_bearer_token(self):
        self.assertTrue(require_bearer_token("Bearer abc", "abc"))
        self.assertFalse(require_bearer_token("Bearer nope", "abc"))
        self.assertFalse(require_bearer_token(None, "abc"))

    def test_sandbox_name(self):
        self.assertEqual(validate_sandbox_name("abc-1"), "abc-1")
        with self.assertRaises(ValueError):
            validate_sandbox_name("bad name")

    def test_packages(self):
        self.assertEqual(validate_packages(["torch==2.8.0"], field="pip"), ["torch==2.8.0"])
        with self.assertRaises(ValueError):
            validate_packages(["bad package"], field="pip")

    def test_allowlist(self):
        self.assertEqual(require_allowlisted(["a"], {"a", "b"}, kind="Secret"), ["a"])
        with self.assertRaises(ValueError):
            require_allowlisted(["c"], {"a", "b"}, kind="Secret")

    def test_paths(self):
        self.assertEqual(validate_remote_path("/tmp/a"), "/tmp/a")
        with self.assertRaises(ValueError):
            validate_remote_path("tmp/a")
        with self.assertRaises(ValueError):
            validate_remote_path("/", allow_root=False)

    def test_network_validation(self):
        self.assertEqual(validate_cidrs(["10.0.0.1/24"], field="cidr"), ["10.0.0.0/24"])
        self.assertEqual(validate_domains(["*.github.com", "pypi.org", "*"]), ["*.github.com", "pypi.org", "*"])
        with self.assertRaises(ValueError):
            validate_cidrs(["not-a-cidr"], field="cidr")

    def test_image_id(self):
        self.assertEqual(validate_image_id("im-abc123"), "im-abc123")
        with self.assertRaises(ValueError):
            validate_image_id("abc")

    def test_bounded_float(self):
        self.assertEqual(bounded_float(2, minimum=1, maximum=4, field="x"), 2.0)
        with self.assertRaises(ValueError):
            bounded_float(5, minimum=1, maximum=4, field="x")


if __name__ == "__main__":
    unittest.main()
